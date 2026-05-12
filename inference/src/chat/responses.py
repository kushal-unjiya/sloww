from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.graph.state import CitationRef


class ChatRequest(BaseModel):
    query: str
    conversation_id: str
    notebook_id: str


class StreamChunk(BaseModel):
    token: str


class CitationPayload(BaseModel):
    citations: list[CitationRef]


class FinalSSEEvent(BaseModel):
    done: bool = True
    citations: list[CitationRef] = []
    chart_payload: dict[str, Any] | None = None
    warning: str | None = None
    llm_calls: list[dict[str, Any]] = Field(default_factory=list)
    latency_seconds: float | None = None

