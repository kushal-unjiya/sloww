from __future__ import annotations

from typing import Literal

from src.graph.state import GraphState


def after_base_query_processor(
    state: GraphState,
) -> Literal["retrieval_engine", "normal_text_generator"]:
    intent = state.intent
    if intent and intent.needs_retrieval:
        return "retrieval_engine"
    return "normal_text_generator"


def after_orchestrator(
    state: GraphState,
) -> Literal["retrieval_engine", "aggregator", "cited_summary_generator"]:
    plan = state.execution_plan
    if plan is None:
        # If orchestrator failed to emit a plan, treat as hard failure upstream.
        return "cited_summary_generator"

    if plan.loop:
        return "retrieval_engine"

    nodes = set(plan.nodes or [])
    if "aggregator" in nodes:
        return "aggregator"
    return "cited_summary_generator"


def after_generation(
    state: GraphState,
) -> Literal["visualizer", "response_assembler"]:
    plan = state.execution_plan
    if plan and "visualizer" in (plan.nodes or []):
        return "visualizer"
    return "response_assembler"

