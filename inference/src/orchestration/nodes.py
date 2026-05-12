from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import Settings
from src.agent.events import emit_agent_event
from src.graph.state import ExecutionPlan, GraphState, IntentTag
from src.orchestration.modules import OrchestrationModules
from src.shared.logging import get_logger, log_event, timer
from src.shared.turn_timing import mark_turn_phase

logger = get_logger("sloww.inference.orchestration.nodes")

_WS_RE = re.compile(r"\s+")
_SECTION_LOOKUP_RE = re.compile(r"\b(section|sec\.?)\s+\d+(?:\.\d+){1,5}\b", re.I)


def _normalize_query(q: str) -> str:
    q2 = q.strip()
    q2 = _WS_RE.sub(" ", q2)
    return q2


def _heuristic_chitchat_intent(normalized_query: str) -> IntentTag | None:
    """Very conservative local classification — avoids an LLM call for common greetings/meta questions."""
    q = normalized_query.strip()
    if len(q) > 120:
        return None
    for pat in _CHITCHAT_INTENT_PATTERNS:
        if pat.match(q):
            return IntentTag(
                needs_retrieval=False,
                multi_doc=False,
                needs_aggregation=False,
                needs_chart=False,
                is_chitchat=True,
                query_type="chitchat",
                complexity="low",
            )
    return None


def format_user_facing_preamble(intent: IntentTag | None, raw_query: str) -> str:
    """Choose a short user-facing status line before the graph starts."""
    q = _normalize_query(raw_query).lower()
    if intent is not None and intent.is_chitchat:
        return "Responding directly…"
    if any(token in q for token in ("summarize", "summary", "summarise")):
        return "I’ll start looking through the documents…"
    if any(token in q for token in ("compare", "difference", "differences", "contrast")):
        return "I’m comparing the sources now…"
    if any(token in q for token in ("cite", "citation", "reference", "sources")):
        return "I’m pulling the most relevant sections first…"
    return "Working on your message…"


# Whole-string patterns only (avoid matching "who is Kushal").
_CHITCHAT_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(hi|hello|hey|yo|hiya|sup)(\s+there)?\s*[!.]?\s*$", re.I),
    re.compile(r"^(good\s+morning|good\s+afternoon|good\s+evening)\s*[!.]?\s*$", re.I),
    re.compile(r"^(thanks|thank you|thx)\s*[!.]?\s*$", re.I),
    re.compile(r"^(goodbye|bye|bye bye)\s*[!.]?\s*$", re.I),
    re.compile(r"^who are you\??\s*$", re.I),
    re.compile(r"^how are you\??\s*$", re.I),
    re.compile(r"^what (is your name|can you do|do you do)\??\s*$", re.I),
    re.compile(r"^(ok|okay|nice|cool|great)\s*[!.]?\s*$", re.I),
)


@dataclass(frozen=True)
class BaseQueryProcessor:
    modules: OrchestrationModules
    settings: Settings

    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()
        normalized = _normalize_query(state.raw_query)
        intent: IntentTag | None = None
        if self.settings.chitchat_intent_heuristic:
            intent = _heuristic_chitchat_intent(normalized)
            if intent is not None:
                logger.info(
                    "intent_classification_heuristic",
                    extra={
                        "event": "intent_classification_heuristic",
                        "node": "base_query_processor",
                        "latency_ms": 0,
                    },
                )
                log_event(
                    logger,
                    "intent_classification_heuristic",
                    node="base_query_processor",
                    latency_ms=0,
                    query_preview=normalized[:160],
                    intent=intent.model_dump(),
                )
                mark_turn_phase("intent_classification_heuristic", latency_ms=0)
        if intent is None:
            # Intent first so chitchat / no-retrieval turns skip HyDE (one fewer slow LLM on Google).
            intent = await self.modules.intent(query=normalized, hypothetical_answer=None)
        should_bypass_hyde = bool(_SECTION_LOOKUP_RE.search(normalized))
        hyde = (
            normalized
            if (not intent.needs_retrieval or should_bypass_hyde)
            else await self.modules.hyde(query=normalized)
        )

        logger.info(
            "base_query_processor_done",
            extra={
                "event": "base_query_processor_done",
                "node": "base_query_processor",
                "latency_ms": t.ms(),
                "needs_retrieval": intent.needs_retrieval,
                "is_chitchat": intent.is_chitchat,
            },
        )
        log_event(
            logger,
            "base_query_processor_done",
            normalized_query=normalized[:160],
            needs_retrieval=intent.needs_retrieval,
            is_chitchat=intent.is_chitchat,
            query_type=intent.query_type,
            complexity=intent.complexity,
            hyde_generated=bool(intent.needs_retrieval and not should_bypass_hyde),
            hyde_bypassed=should_bypass_hyde,
        )
        mark_turn_phase(
            "base_query_processor",
            latency_ms=t.ms(),
            needs_retrieval=intent.needs_retrieval,
            is_chitchat=intent.is_chitchat,
        )
        return state.model_copy(
            update={
                "normalized_query": normalized,
                "expanded_query": hyde,
                "intent": intent,
            }
        )


@dataclass(frozen=True)
class Orchestrator:
    modules: OrchestrationModules
    settings: Settings

    async def __call__(self, state: GraphState) -> GraphState:
        t = timer()
        if state.intent is None:
            raise RuntimeError("intent missing from state")

        await emit_agent_event(
            agent_id="answer-supervisor",
            label="Answer supervisor",
            role="supervisor",
            phase="start",
            message="Checking evidence coverage and deciding the next step.",
            input_preview=(state.normalized_query or state.raw_query)[:240],
            metadata={"retrieved_chunk_count": len(state.retrieved_chunks)},
        )

        # Coverage scoring uses retrieved chunks (text only).
        chunk_texts = [c.raw_text for c in state.retrieved_chunks[:12]]
        coverage_score = await self.modules.coverage(query=state.normalized_query or state.raw_query, chunks=chunk_texts)

        loop_count = state.loop_count
        if coverage_score < self.settings.coverage_threshold and loop_count < self.settings.loop_max:
            loop_count += 1
            plan = ExecutionPlan(nodes=["retrieval_engine", "orchestrator"], loop=True, refined_query=None)
            logger.info(
                "retrieval_loop_triggered",
                extra={
                    "event": "retrieval_loop_triggered",
                    "node": "orchestrator",
                    "latency_ms": t.ms(),
                    "coverage_score": coverage_score,
                    "threshold": self.settings.coverage_threshold,
                    "loop_count": loop_count,
                },
            )
            log_event(
                logger,
                "retrieval_loop_triggered",
                coverage_score=coverage_score,
                threshold=self.settings.coverage_threshold,
                loop_count=loop_count,
                chunk_count=len(state.retrieved_chunks),
                query_preview=(state.normalized_query or state.raw_query)[:160],
            )
            mark_turn_phase(
                "retrieval_loop_trigger",
                latency_ms=t.ms(),
                coverage_score=coverage_score,
                loop_count=loop_count,
            )
            await emit_agent_event(
                agent_id="answer-supervisor",
                label="Answer supervisor",
                role="supervisor",
                phase="progress",
                message="Evidence coverage is weak, so retrieval will run again.",
                metadata={
                    "coverage_score": coverage_score,
                    "threshold": self.settings.coverage_threshold,
                    "loop_count": loop_count,
                },
            )
            return state.model_copy(
                update={
                    "retrieval_coverage": coverage_score,
                    "execution_plan": plan,
                    "loop_count": loop_count,
                }
            )

        # Otherwise plan next nodes.
        summary = "\n".join(f"[{c.doc_id}] {c.raw_text[:180]}" for c in state.retrieved_chunks[:8])
        plan = await self.modules.planner(
            query=state.normalized_query or state.raw_query,
            intent=state.intent,
            chunk_summary=summary,
        )

        # Ensure essential nodes exist.
        nodes = plan.nodes or []
        if state.intent.is_chitchat:
            nodes = ["normal_text_generator", "response_assembler"]
        else:
            if "cited_summary_generator" not in nodes and "normal_text_generator" not in nodes:
                nodes.append("cited_summary_generator")
            if state.intent.needs_aggregation and "aggregator" not in nodes:
                nodes.insert(0, "aggregator")
            if state.intent.needs_chart and "visualizer" not in nodes:
                nodes.append("visualizer")
            if "response_assembler" not in nodes:
                nodes.append("response_assembler")

        plan = plan.model_copy(update={"nodes": nodes, "loop": False})
        logger.info(
            "orchestrator_done",
            extra={
                "event": "orchestrator_done",
                "node": "orchestrator",
                "latency_ms": t.ms(),
                "coverage_score": coverage_score,
                "threshold": self.settings.coverage_threshold,
                "plan_nodes": nodes,
                "loop_count": loop_count,
                "is_chitchat": state.intent.is_chitchat,
            },
        )
        log_event(
            logger,
            "orchestrator_done",
            coverage_score=coverage_score,
            threshold=self.settings.coverage_threshold,
            plan_nodes=nodes,
            loop_count=loop_count,
            is_chitchat=state.intent.is_chitchat,
            retrieved_chunk_count=len(state.retrieved_chunks),
            query_preview=(state.normalized_query or state.raw_query)[:160],
        )
        mark_turn_phase(
            "orchestrator_node",
            latency_ms=t.ms(),
            coverage_score=coverage_score,
            plan_nodes=nodes,
        )
        await emit_agent_event(
            agent_id="answer-supervisor",
            label="Answer supervisor",
            role="supervisor",
            phase="end",
            message="Answer plan selected.",
            output_preview=", ".join(nodes),
            metadata={
                "coverage_score": coverage_score,
                "threshold": self.settings.coverage_threshold,
                "loop_count": loop_count,
                "plan_nodes": nodes,
            },
        )

        return state.model_copy(
            update={
                "retrieval_coverage": coverage_score,
                "execution_plan": plan,
            }
        )
