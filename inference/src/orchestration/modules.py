from __future__ import annotations

from dataclasses import dataclass

from src.graph.state import ExecutionPlan, IntentTag
from src.shared.clients.llm_client import LLMClient
from src.shared.llm_json import parse_llm_json_object
from src.shared.logging import get_logger, log_event, timer
from src.shared.turn_timing import mark_turn_phase

logger = get_logger("sloww.inference.orchestration.modules")


@dataclass
class HyDEExpander:
    llm: LLMClient

    async def __call__(self, *, query: str) -> str:
        t = timer()
        prompt = (
            "You are generating a hypothetical passage that would answer the user's question. "
            "Write a concise, information-dense paragraph (no preface, no citations) that could appear in a document.\n\n"
            f"Question: {query}\n"
            "Hypothetical passage:"
        )
        res = await self.llm.complete(prompt=prompt)
        logger.info(
            "hyde_expansion",
            extra={
                "event": "hyde_expansion",
                "component": "hyde_expansion",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
            },
        )
        log_event(
            logger,
            "hyde_expansion",
            provider=res.provider,
            model=res.model,
            latency_ms=t.ms(),
            query_preview=query[:160],
            output_preview=res.text[:160],
        )
        mark_turn_phase("hyde_expansion", latency_ms=t.ms())
        return res.text.strip()


@dataclass
class IntentClassifier:
    llm: LLMClient

    async def __call__(self, *, query: str, hypothetical_answer: str | None = None) -> IntentTag:
        t = timer()
        hyde_line = (
            f"Hypothetical answer: {hypothetical_answer}\n"
            if hypothetical_answer is not None
            else "Hypothetical answer: (not generated — classify using only the query.)\n"
        )
        prompt = (
            "Classify the user's query into a structured intent object. "
            "Return ONLY valid JSON (no markdown).\n\n"
            "Schema:\n"
            "{\n"
            '  "needs_retrieval": bool,\n'
            '  "multi_doc": bool,\n'
            '  "needs_aggregation": bool,\n'
            '  "needs_chart": bool,\n'
            '  "is_chitchat": bool,\n'
            '  "query_type": "fact|howto|analysis|definition|chitchat|other",\n'
            '  "complexity": "low|medium|high"\n'
            "}\n\n"
            "Few-shot examples:\n"
            "Input: query='hi how are you'\n"
            'Output: {"needs_retrieval": false, "multi_doc": false, "needs_aggregation": false, "needs_chart": false, "is_chitchat": true, "query_type": "chitchat", "complexity": "low"}\n'
            "Input: query='Compare the claims in the two documents about transformer scaling laws'\n"
            'Output: {"needs_retrieval": true, "multi_doc": true, "needs_aggregation": true, "needs_chart": false, "is_chitchat": false, "query_type": "analysis", "complexity": "high"}\n\n'
            f"Query: {query}\n"
            f"{hyde_line}"
            "Output JSON:"
        )
        res = await self.llm.complete(prompt=prompt)
        data = parse_llm_json_object(res.text)
        intent = IntentTag.model_validate(data)
        logger.info(
            "intent_classification",
            extra={
                "event": "intent_classification",
                "component": "intent_classification",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
                "intent": intent.model_dump(),
            },
        )
        log_event(
            logger,
            "intent_classification",
            provider=res.provider,
            model=res.model,
            latency_ms=t.ms(),
            intent=intent.model_dump(),
            query_preview=query[:160],
        )
        mark_turn_phase("intent_classification", latency_ms=t.ms())
        return intent


@dataclass
class CoverageScorer:
    llm: LLMClient

    async def __call__(self, *, query: str, chunks: list[str]) -> float:
        t = timer()
        chunk_summary = "\n\n".join(f"- {c[:240]}" for c in chunks[:8])
        prompt = (
            "Score how well the provided retrieved chunks cover the user's question. "
            "Return ONLY a number between 0.0 and 1.0.\n\n"
            f"Query: {query}\n\n"
            f"Chunks:\n{chunk_summary}\n\n"
            "Coverage score:"
        )
        res = await self.llm.complete(prompt=prompt)
        raw = res.text.strip().split()[0]
        score = float(raw)
        logger.info(
            "coverage_scoring",
            extra={
                "event": "coverage_scoring",
                "component": "coverage_scoring",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
                "score": score,
            },
        )
        log_event(
            logger,
            "coverage_scoring",
            provider=res.provider,
            model=res.model,
            latency_ms=t.ms(),
            score=score,
            query_preview=query[:160],
            chunk_count=len(chunks),
        )
        mark_turn_phase("coverage_scoring", latency_ms=t.ms(), score=score)
        return score


@dataclass
class OrchestratorModule:
    llm: LLMClient

    async def __call__(self, *, query: str, intent: IntentTag, chunk_summary: str) -> ExecutionPlan:
        t = timer()
        prompt = (
            "You are a planner deciding which pipeline nodes to run.\n"
            "Return ONLY valid JSON (no markdown).\n\n"
            "Allowed nodes: [\"retrieval_engine\",\"orchestrator\",\"aggregator\",\"cited_summary_generator\",\"normal_text_generator\",\"visualizer\",\"response_assembler\"]\n"
            "Schema:\n"
            "{\n"
            '  "nodes": string[],\n'
            '  "parallel": bool,\n'
            '  "loop": bool,\n'
            '  "refined_query": string|null\n'
            "}\n\n"
            "Guidelines:\n"
            "- If intent.is_chitchat true: nodes=[\"normal_text_generator\",\"response_assembler\"]\n"
            "- If intent.needs_aggregation true: include \"aggregator\"\n"
            "- Always include \"cited_summary_generator\" for retrieval-grounded answers\n"
            "- Include \"visualizer\" only when intent.needs_chart is true\n\n"
            f"Query: {query}\n"
            f"Intent: {intent.model_dump()}\n"
            f"Chunk summary: {chunk_summary[:1200]}\n"
            "Output JSON:"
        )
        res = await self.llm.complete(prompt=prompt)
        data = parse_llm_json_object(res.text)
        plan = ExecutionPlan.model_validate(data)
        logger.info(
            "orchestrator_plan",
            extra={
                "event": "orchestrator",
                "component": "orchestrator",
                "provider": res.provider,
                "model": res.model,
                "latency_ms": t.ms(),
                "plan_nodes": plan.nodes,
                "loop": plan.loop,
            },
        )
        log_event(
            logger,
            "orchestrator_plan",
            provider=res.provider,
            model=res.model,
            latency_ms=t.ms(),
            plan_nodes=plan.nodes,
            loop=plan.loop,
            refined_query=plan.refined_query,
        )
        mark_turn_phase(
            "orchestrator_plan",
            latency_ms=t.ms(),
            plan_nodes=plan.nodes,
            loop=plan.loop,
        )
        return plan


@dataclass(frozen=True)
class OrchestrationModules:
    hyde: HyDEExpander
    intent: IntentClassifier
    planner: OrchestratorModule
    coverage: CoverageScorer
