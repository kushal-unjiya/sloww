from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IntentTag(BaseModel):
    needs_retrieval: bool = True
    multi_doc: bool = False
    needs_aggregation: bool = False
    needs_chart: bool = False
    is_chitchat: bool = False
    query_type: str = "unknown"
    complexity: str = "medium"


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    notebook_id: str
    page: int | None = None
    char_offset: int | None = None
    raw_text: str
    score: float
    source: Literal["dense", "sparse"] = "dense"
    original_filename: str | None = None


class ExecutionPlan(BaseModel):
    nodes: list[str] = Field(default_factory=list)
    parallel: bool = False
    loop: bool = False
    refined_query: str | None = None


class Conflict(BaseModel):
    topic: str
    doc_a_claim: str
    doc_b_claim: str
    chunk_ids_a: list[str] = Field(default_factory=list)
    chunk_ids_b: list[str] = Field(default_factory=list)
    conflict_type: Literal["ontological", "mathematical", "interpretive"]


class AggregatorOutput(BaseModel):
    agreements: list[str] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    consolidated: str = ""
    reasoning_trace: str = ""


class CitationRef(BaseModel):
    chunk_id: str
    ref_num: int
    doc_title: str | None = None
    author: str | None = None
    page: int | None = None
    excerpt_80: str | None = None
    document_id: str | None = None
    raw_text: str | None = None


class CitedAnswer(BaseModel):
    text: str
    citations: list[CitationRef] = Field(default_factory=list)
    assertion_failed: bool = False


class FinalResponse(BaseModel):
    answer_text: str
    citations: list[CitationRef] = Field(default_factory=list)
    chart_payload: dict | None = None
    stream_ready: bool = True
    warning: str | None = None


class GraphState(BaseModel):
    # Request identity
    raw_query: str
    session_id: str
    notebook_id: str
    request_id: str

    # Derived
    normalized_query: str | None = None
    expanded_query: str | None = None

    intent: IntentTag | None = None

    # Retrieval
    retrieved_chunks: list[Chunk] = Field(default_factory=list)
    retrieval_coverage: float | None = None

    # Planning / loop
    execution_plan: ExecutionPlan | None = None
    loop_count: int = 0

    # Generation
    aggregator_output: AggregatorOutput | None = None
    cited_answer: CitedAnswer | None = None
    final_response: FinalResponse | None = None

