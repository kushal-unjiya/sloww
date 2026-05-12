from __future__ import annotations

from dataclasses import dataclass

from src.generation.modules import (
    AggregatorModule,
    CitedSummaryModule,
    NormalTextModule,
    VisualizerModule,
    build_structure_hints,
    _extract_chunk_ids,
    every_claim_has_chunk_id,
    explain_citation_assertion_failure,
    repair_citations_with_fallback,
)
from src.agent.events import emit_agent_event
from src.graph.state import (
    CitedAnswer,
    CitationRef,
    FinalResponse,
    GraphState,
)
from src.shared.logging import get_logger, log_event, timer
from src.shared.turn_timing import mark_turn_phase

logger = get_logger("sloww.inference.generation.nodes")

_RAW_TEXT_CAP = 12_000


@dataclass(frozen=True)
class GenerationModules:
    aggregator: AggregatorModule
    cited: CitedSummaryModule
    normal: NormalTextModule
    visualizer: VisualizerModule


@dataclass(frozen=True)
class Aggregator:
    modules: GenerationModules

    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()
        # Split chunks by doc_id; aggregate top 2 docs if present.
        by_doc: dict[str, list[str]] = {}
        for c in state.retrieved_chunks:
            by_doc.setdefault(c.doc_id, []).append(f"- {c.chunk_id}: {c.raw_text[:420]}")

        doc_ids = list(by_doc.keys())
        if len(doc_ids) < 2:
            # Nothing to aggregate; degrade gracefully.
            logger.warning(
                "aggregator_skipped_insufficient_docs",
                extra={"event": "aggregator_skipped", "node": "aggregator", "latency_ms": t.ms()},
            )
            log_event(
                logger,
                "aggregator_skipped_insufficient_docs",
                retrieved_chunk_count=len(state.retrieved_chunks),
                unique_doc_count=len(doc_ids),
                query_preview=(state.normalized_query or state.raw_query)[:160],
            )
            return state

        a, b = doc_ids[0], doc_ids[1]
        out = await self.modules.aggregator(
            query=state.normalized_query or state.raw_query,
            doc_a_chunks="\n".join(by_doc[a][:10]),
            doc_b_chunks="\n".join(by_doc[b][:10]),
        )
        logger.info(
            "aggregator_done",
            extra={"event": "aggregator_done", "node": "aggregator", "latency_ms": t.ms()},
        )
        log_event(
            logger,
            "aggregator_done",
            retrieved_chunk_count=len(state.retrieved_chunks),
            unique_doc_count=len(doc_ids),
            output_preview=out.consolidated[:200],
        )
        return state.model_copy(update={"aggregator_output": out})


@dataclass(frozen=True)
class CitedSummaryGenerator:
    modules: GenerationModules
    max_assert_retries: int = 0

    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()
        await emit_agent_event(
            agent_id="citation-writer",
            label="Citation writer",
            role="writer",
            phase="start",
            message="Drafting a grounded answer from the selected evidence.",
            input_preview=(state.normalized_query or state.raw_query)[:240],
            metadata={"chunk_count": len(state.retrieved_chunks)},
        )
        consolidated = state.aggregator_output.consolidated if state.aggregator_output else ""
        chunk_lines = [f"- {c.chunk_id}: {c.raw_text[:520]}" for c in state.retrieved_chunks[:36]]
        source_chunks = "\n".join(chunk_lines)
        structure_hints = build_structure_hints(source_chunks)
        chunk_ids = [c.chunk_id for c in state.retrieved_chunks if c.chunk_id]

        last_text = ""
        for attempt in range(1, self.max_assert_retries + 2):
            try:
                ans = await self.modules.cited(
                    query=state.normalized_query or state.raw_query,
                    consolidated=consolidated,
                    source_chunks=source_chunks,
                    structure_hints=structure_hints,
                )
            except Exception as exc:
                logger.exception(
                    "cited_summary_failed_degraded",
                    extra={
                        "event": "cited_summary_failed_degraded",
                        "node": "cited_summary_generator",
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    },
                )
                log_event(
                    logger,
                    "cited_summary_failed_degraded",
                    attempt=attempt,
                    query_preview=(state.normalized_query or state.raw_query)[:160],
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:500],
                )
                fallback = (
                    "I found some source material, but the language model failed while drafting the grounded answer. "
                    "Please try again in a moment."
                )
                cited = CitedAnswer(text=fallback, citations=[], assertion_failed=True)
                return state.model_copy(update={"cited_answer": cited})
            last_text = ans.text.strip()
            trial = last_text
            if not every_claim_has_chunk_id(trial):
                trial = repair_citations_with_fallback(trial, chunk_ids)
            if every_claim_has_chunk_id(trial):
                if trial != last_text:
                    logger.info(
                        "citation_lines_repaired",
                        extra={
                            "event": "citation_lines_repaired",
                            "node": "cited_summary_generator",
                            "attempt": attempt,
                            "latency_ms": t.ms(),
                            },
                        )
                    log_event(
                        logger,
                        "citation_lines_repaired",
                        attempt=attempt,
                        query_preview=(state.normalized_query or state.raw_query)[:160],
                        repaired_preview=trial[:200],
                    )
                cited = CitedAnswer(text=trial, citations=[], assertion_failed=False)
                logger.info(
                    "citation_assertion_passed",
                    extra={
                        "event": "assertion_passed",
                        "node": "cited_summary_generator",
                        "attempt": attempt,
                        "repaired": trial != last_text,
                        "latency_ms": t.ms(),
                    },
                )
                log_event(
                    logger,
                    "citation_assertion_passed",
                    attempt=attempt,
                    repaired=(trial != last_text),
                    citations_count=len(cited.citations),
                )
                await emit_agent_event(
                    agent_id="citation-writer",
                    label="Citation writer",
                    role="writer",
                    phase="end",
                    message="Grounded answer passed citation checks.",
                    output_preview=trial[:300],
                    metadata={"attempt": attempt, "repaired": trial != last_text},
                )
                return state.model_copy(update={"cited_answer": cited})

            logger.warning(
                "citation_assertion_retry",
                extra={
                    "event": "assertion_retry",
                    "node": "cited_summary_generator",
                    "attempt": attempt,
                    "assert_detail": explain_citation_assertion_failure(last_text),
                },
            )

        # Degraded path: keep text, mark assertion_failed, stream continues.
        logger.error(
            "citation_assertion_failed_degraded",
            extra={
                "event": "assertion_failed",
                "node": "cited_summary_generator",
                "latency_ms": t.ms(),
                "assert_detail": explain_citation_assertion_failure(last_text),
            },
        )
        log_event(
            logger,
            "citation_assertion_failed_degraded",
            attempt=self.max_assert_retries + 1,
            query_preview=(state.normalized_query or state.raw_query)[:160],
            assert_detail=explain_citation_assertion_failure(last_text),
        )
        cited = CitedAnswer(text=last_text, citations=[], assertion_failed=True)
        await emit_agent_event(
            agent_id="citation-writer",
            label="Citation writer",
            role="writer",
            phase="error",
            message="Citation checks failed; returning degraded answer.",
            output_preview=last_text[:300],
            metadata={"attempts": self.max_assert_retries + 1},
        )
        return state.model_copy(update={"cited_answer": cited})


@dataclass(frozen=True)
class NormalTextGenerator:
    modules: GenerationModules

    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()
        text_out = await self.modules.normal(query=state.normalized_query or state.raw_query)
        cited = CitedAnswer(text=text_out, citations=[], assertion_failed=False)
        logger.info(
            "normal_text_done",
            extra={"event": "normal_text_done", "node": "normal_text_generator", "latency_ms": t.ms()},
        )
        log_event(
            logger,
            "normal_text_done",
            query_preview=(state.normalized_query or state.raw_query)[:160],
            output_preview=text_out[:200],
        )
        return state.model_copy(update={"cited_answer": cited})


@dataclass(frozen=True)
class Visualizer:
    modules: GenerationModules

    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()
        try:
            await emit_agent_event(
                agent_id="chart-agent",
                label="Chart agent",
                role="visualizer",
                phase="start",
                message="Checking whether the answer can be turned into a chart.",
                input_preview=(state.normalized_query or state.raw_query)[:240],
            )
            payload = await self.modules.visualizer(
                query=state.normalized_query or state.raw_query,
                data_payload=state.cited_answer.text if state.cited_answer else "",
            )
            fr = state.final_response or FinalResponse(answer_text=state.cited_answer.text if state.cited_answer else "")
            fr = fr.model_copy(update={"chart_payload": payload})
            logger.info(
                "visualizer_done",
                extra={"event": "visualizer_done", "node": "visualizer", "latency_ms": t.ms()},
            )
            log_event(
                logger,
                "visualizer_done",
                query_preview=(state.normalized_query or state.raw_query)[:160],
                chart_type=payload.get("chart_type"),
            )
            await emit_agent_event(
                agent_id="chart-agent",
                label="Chart agent",
                role="visualizer",
                phase="end",
                message="Chart payload generated.",
                output_preview=str(payload)[:300],
                metadata={"chart_type": payload.get("chart_type")},
            )
            return state.model_copy(update={"final_response": fr})
        except Exception:
            # Soft degrade: omit chart.
            logger.exception(
                "visualizer_failed_degraded",
                extra={"event": "visualizer_failed", "node": "visualizer", "latency_ms": t.ms()},
            )
            log_event(
                logger,
                "visualizer_failed_degraded",
                query_preview=(state.normalized_query or state.raw_query)[:160],
            )
            await emit_agent_event(
                agent_id="chart-agent",
                label="Chart agent",
                role="visualizer",
                phase="error",
                message="Chart generation failed; continuing without a chart.",
            )
            return state


@dataclass(frozen=True)
class ResponseAssembler:
    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()

        answer_text = state.cited_answer.text if state.cited_answer else ""
        citations: list[CitationRef] = []

        seen_ids: set[str] = set()
        chunk_ids: list[str] = []
        for cid in _extract_chunk_ids(answer_text):
            if cid not in seen_ids:
                seen_ids.add(cid)
                chunk_ids.append(cid)

        by_chunk = {c.chunk_id: c for c in state.retrieved_chunks}
        if chunk_ids:
            for i, cid in enumerate(chunk_ids, start=1):
                c = by_chunk.get(cid)
                excerpt = (c.raw_text[:80] if c and c.raw_text else None) if c else None
                raw = (c.raw_text if c and c.raw_text else None) if c else None
                if raw is not None and len(raw) > _RAW_TEXT_CAP:
                    raw = raw[:_RAW_TEXT_CAP] + "…"
                citations.append(
                    CitationRef(
                        chunk_id=cid,
                        ref_num=i,
                        doc_title=(c.original_filename if c else None) or None,
                        author=None,
                        page=c.page if c else None,
                        excerpt_80=excerpt,
                        document_id=c.doc_id if c else None,
                        raw_text=raw,
                    )
                )

        display_text = answer_text
        for c in citations:
            display_text = display_text.replace(f"[{c.chunk_id}]", f"[{c.ref_num}]")

        warning = None
        if state.cited_answer and state.cited_answer.assertion_failed:
            warning = "Some claims may be missing citations (degraded mode)."

        if not display_text.strip():
            if state.intent and state.intent.is_chitchat:
                display_text = "Hello! How can I help you today?"
            elif state.retrieved_chunks:
                display_text = (
                    "I looked through the available sources, but I could not assemble a confident grounded answer yet. "
                    "Try asking a narrower question or add more relevant sources."
                )
                warning = warning or "insufficient_source_coverage"
            else:
                display_text = (
                    "I could not find enough source material for this question yet. "
                    "Try adding documents or rephrasing the query."
                )
                warning = warning or "no_source_material"

        fr = FinalResponse(
            answer_text=display_text,
            citations=citations,
            chart_payload=(state.final_response.chart_payload if state.final_response else None),
            stream_ready=True,
            warning=warning,
        )
        logger.info(
            "response_assembler_done",
            extra={
                "event": "response_assembler_done",
                "node": "response_assembler",
                "latency_ms": t.ms(),
                "citations_count": len(citations),
            },
        )
        log_event(
            logger,
            "response_assembler_done",
            query_preview=(state.normalized_query or state.raw_query)[:160],
            answer_length=len(display_text),
            citations_count=len(citations),
            warning=warning,
            stream_ready=fr.stream_ready,
        )
        mark_turn_phase("response_assembler", latency_ms=t.ms(), citations_count=len(citations))
        return state.model_copy(update={"final_response": fr})
