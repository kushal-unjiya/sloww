from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import get_settings
from src.graph.state import GraphState
from src.graph.builder import ChatGraphBuilder, GraphConfig
from src.shared.clients.embedding_client import EmbeddingClient
from src.shared.clients.llm_client import LLMClient, LLMResult
from src.shared.clients.qdrant_client import QdrantClientWrapper
from src.retrieval.reranker import CrossEncoderReranker


class StubLLM(LLMClient):
    async def complete(self, *, prompt: str, stream_final_answer: bool = False) -> LLMResult:  # type: ignore[override]
        # Detect which module based on prompt hints.
        if "Hypothetical passage:" in prompt:
            return LLMResult(text="A hypothetical answer.", provider="stub", model="stub", latency_ms=1)
        if "Schema" in prompt and "needs_retrieval" in prompt:
            # Chitchat route.
            return LLMResult(
                text=json.dumps(
                    {
                        "needs_retrieval": False,
                        "multi_doc": False,
                        "needs_aggregation": False,
                        "needs_chart": False,
                        "is_chitchat": True,
                        "query_type": "chitchat",
                        "complexity": "low",
                    }
                ),
                provider="stub",
                model="stub",
                latency_ms=1,
            )
        if "Assistant:" in prompt:
            return LLMResult(text="Hello! How can I help you today?", provider="stub", model="stub", latency_ms=1)
        # Default for other calls.
        return LLMResult(text="{}", provider="stub", model="stub", latency_ms=1)


@pytest.mark.asyncio
async def test_graph_runs_chitchat_path() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    llm = StubLLM(settings=settings)
    embedding = EmbeddingClient(settings=settings)
    qdrant = QdrantClientWrapper(url=settings.qdrant_url, api_key=None, collection=settings.qdrant_collection)

    # Avoid loading a real cross encoder in unit tests.
    cross = CrossEncoderReranker.__new__(CrossEncoderReranker)  # type: ignore[misc]
    cross.model_name = "stub"
    cross._model = None  # type: ignore[attr-defined]
    cross.rerank = lambda *, query, chunks, top_n: chunks[:top_n]  # type: ignore[method-assign]

    graph = ChatGraphBuilder(
        config=GraphConfig(
            settings=settings,
            llm_client=llm,
            llm_router=llm,
            embedding_client=embedding,
            qdrant_client=qdrant,
            pg_engine=engine,
            cross_encoder=cross,
        )
    ).build()

    state = {
        "raw_query": "hi",
        "session_id": "conv_1",
        "notebook_id": "nb_1",
        "request_id": "req_1",
    }
    out = await graph.ainvoke(state)
    gs = GraphState.model_validate(out)
    assert gs.final_response is not None
    assert "Hello" in gs.final_response.answer_text

