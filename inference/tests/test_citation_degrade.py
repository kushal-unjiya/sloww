from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import get_settings
from src.graph.builder import ChatGraphBuilder, GraphConfig
from src.graph.state import GraphState
from src.shared.clients.embedding_client import EmbeddingClient, EmbeddingResult
from src.shared.clients.llm_client import LLMClient, LLMResult
from src.shared.clients.qdrant_client import QdrantClientWrapper
from src.retrieval.reranker import CrossEncoderReranker


class StubLLM(LLMClient):
    async def complete(self, *, prompt: str, stream_final_answer: bool = False) -> LLMResult:  # type: ignore[override]
        if "Hypothetical passage:" in prompt:
            return LLMResult(text="Hypothetical chunk about X.", provider="stub", model="stub", latency_ms=1)
        if "Schema" in prompt and "needs_retrieval" in prompt:
            return LLMResult(
                text=json.dumps(
                    {
                        "needs_retrieval": True,
                        "multi_doc": False,
                        "needs_aggregation": False,
                        "needs_chart": False,
                        "is_chitchat": False,
                        "query_type": "fact",
                        "complexity": "low",
                    }
                ),
                provider="stub",
                model="stub",
                latency_ms=1,
            )
        if "Coverage score:" in prompt:
            return LLMResult(text="0.99", provider="stub", model="stub", latency_ms=1)
        if "Allowed nodes" in prompt:
            return LLMResult(
                text=json.dumps({"nodes": ["cited_summary_generator", "response_assembler"], "parallel": False, "loop": False, "refined_query": None}),
                provider="stub",
                model="stub",
                latency_ms=1,
            )
        if "Every line MUST end with a citation bracket" in prompt:
            # Purposely missing citations -> local repair appends fallback chunk id from retrieval.
            return LLMResult(text="This answer has no citations.", provider="stub", model="stub", latency_ms=1)
        return LLMResult(text="{}", provider="stub", model="stub", latency_ms=1)


@pytest.mark.asyncio
async def test_cited_summary_repairs_uncited_answer_with_fallback_chunk_id() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    # Create minimal tables used by ResponseAssembler.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS chunks_metadata (
                  chunk_id TEXT PRIMARY KEY,
                  doc_id TEXT,
                  notebook_id TEXT,
                  page INTEGER,
                  char_offset INTEGER,
                  raw_text TEXT,
                  doc_title TEXT,
                  author TEXT
                )
                """
            )
        )
        await conn.execute(
            text(
                """
                INSERT INTO chunks_metadata (chunk_id, doc_id, notebook_id, page, char_offset, raw_text, doc_title, author)
                VALUES ('chunk_1', 'doc_1', 'nb_1', 1, 0, 'Some text', 'Doc', 'Author')
                """
            )
        )

    llm = StubLLM(settings=settings)
    embedding = EmbeddingClient(settings=settings)
    qdrant = QdrantClientWrapper(url=settings.qdrant_url, api_key=None, collection=settings.qdrant_collection)

    # Stub embedding + qdrant so retrieval doesn't hit network.
    async def _embed(_text: str) -> EmbeddingResult:
        return EmbeddingResult(vector=[0.0, 0.0, 0.0], provider="stub", model=settings.embedding_model, dim=3)

    embedding.embed = _embed  # type: ignore[method-assign]
    qdrant.search = lambda *, vector, query_filter, limit, with_payload=True, collection_name=None, **_: [  # type: ignore[method-assign]
        {"id": "chunk_1", "score": 0.9, "payload": {"chunk_id": "chunk_1", "doc_id": "doc_1", "notebook_id": "nb_1", "raw_text": "Some text"}}
    ]

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

    out = await graph.ainvoke(
        {
            "raw_query": "What is X?",
            "session_id": "conv_1",
            "notebook_id": "nb_1",
            "request_id": "req_1",
        }
    )
    gs = GraphState.model_validate(out)
    assert gs.final_response is not None
    assert gs.final_response.warning is None
    assert gs.cited_answer is not None
    assert gs.cited_answer.assertion_failed is False
    # ResponseAssembler rewrites [chunk_id] to display refs like [1]
    assert any(c.chunk_id == "chunk_1" for c in gs.final_response.citations)
    assert "[1]" in (gs.final_response.answer_text or "")

