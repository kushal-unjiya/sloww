from __future__ import annotations

from src.graph.edges import after_base_query_processor, after_generation, after_orchestrator
from src.graph.state import ExecutionPlan, GraphState, IntentTag


def test_after_base_query_processor_routes() -> None:
    s = GraphState(raw_query="hi", session_id="c", notebook_id="n", request_id="r", intent=IntentTag(needs_retrieval=False))
    assert after_base_query_processor(s) == "normal_text_generator"

    s2 = s.model_copy(update={"intent": IntentTag(needs_retrieval=True)})
    assert after_base_query_processor(s2) == "retrieval_engine"


def test_after_orchestrator_routes() -> None:
    s = GraphState(raw_query="q", session_id="c", notebook_id="n", request_id="r")
    s = s.model_copy(update={"execution_plan": ExecutionPlan(loop=True)})
    assert after_orchestrator(s) == "retrieval_engine"

    s = s.model_copy(update={"execution_plan": ExecutionPlan(nodes=["aggregator"], loop=False)})
    assert after_orchestrator(s) == "aggregator"

    s = s.model_copy(update={"execution_plan": ExecutionPlan(nodes=["cited_summary_generator"], loop=False)})
    assert after_orchestrator(s) == "cited_summary_generator"


def test_after_generation_routes() -> None:
    s = GraphState(raw_query="q", session_id="c", notebook_id="n", request_id="r")
    s = s.model_copy(update={"execution_plan": ExecutionPlan(nodes=["visualizer"])})
    assert after_generation(s) == "visualizer"

