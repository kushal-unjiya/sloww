from __future__ import annotations

from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from src.config import Settings
from src.graph.state import Chunk
from src.shared.clients.embedding_client import EmbeddingClient
from src.shared.clients.qdrant_client import QdrantClientWrapper
from src.shared.logging import get_logger, log_event, timer

logger = get_logger("sloww.inference.retrieval.dense")


class QdrantRetriever:
    def __init__(
        self,
        *,
        settings: Settings,
        embedding_client: EmbeddingClient,
        qdrant_client: QdrantClientWrapper,
        top_k: int,
    ) -> None:
        self._settings = settings
        self._embed = embedding_client
        self._qdrant = qdrant_client
        self._top_k = top_k

    def _collection_name(self, notebook_id: str) -> str:
        return f"{self._settings.qdrant_collection_prefix}{notebook_id}"

    async def __call__(self, *, notebook_id: str, hyde_text: str) -> list[Chunk]:
        t = timer()
        emb = await self._embed.embed(hyde_text)
        query_filter = Filter(
            must=[FieldCondition(key="notebook_id", match=MatchValue(value=notebook_id))]
        )
        collection_name = self._collection_name(notebook_id)

        hits = self._qdrant.search(
            vector=emb.vector,
            query_filter=query_filter,
            limit=self._top_k,
            collection_name=collection_name,
        )
        chunks: list[Chunk] = []
        for h in hits:
            p = h.get("payload") or {}
            page = p.get("page_number")
            if page is None:
                page = p.get("page")
            if page is not None:
                try:
                    page = int(page)
                except (TypeError, ValueError):
                    page = None
            orig = p.get("original_filename")
            chunks.append(
                Chunk(
                    chunk_id=str(p.get("chunk_id") or h.get("id")),
                    doc_id=str(p.get("doc_id") or p.get("document_id") or ""),
                    notebook_id=str(p.get("notebook_id") or notebook_id),
                    page=page,
                    char_offset=p.get("char_offset"),
                    raw_text=str(p.get("raw_text") or p.get("text") or ""),
                    score=float(h.get("score") or 0.0),
                    source="dense",
                    original_filename=str(orig) if orig is not None else None,
                )
            )

        logger.info(
            "dense_retrieval_done",
            extra={
                "event": "dense_retrieval_done",
                "substage": "qdrant_search",
                "latency_ms": t.ms(),
                "results_count": len(chunks),
                "collection": collection_name,
            },
        )
        log_event(
            logger,
            "dense_retrieval_done",
            collection=collection_name,
            notebook_id=notebook_id,
            results_count=len(chunks),
            query_preview=hyde_text[:160],
            top_chunk_ids=[c.chunk_id for c in chunks[:5]],
        )
        return chunks
