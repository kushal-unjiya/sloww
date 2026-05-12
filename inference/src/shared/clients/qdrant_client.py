from __future__ import annotations

from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter

from src.shared.logging import get_logger, log_event, timer

logger = get_logger("sloww.inference.qdrant")


class QdrantClientWrapper:
    def __init__(self, *, url: str, api_key: str | None, collection: str) -> None:
        self._collection = collection
        self._client = QdrantClient(url=url, api_key=api_key)

    @property
    def collection(self) -> str:
        return self._collection

    def search(
        self,
        *,
        vector: list[float],
        query_filter: Filter | None,
        limit: int,
        with_payload: bool = True,
        collection_name: str | None = None,
    ) -> list[dict[str, Any]]:
        coll = collection_name or self._collection
        if query_filter is None:
            raise ValueError("Qdrant search missing query_filter (notebook_id security boundary)")

        t = timer()
        resp = self._client.query_points(
            collection_name=coll,
            query=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=with_payload,
        )
        hits = resp.points
        logger.info(
            "qdrant_search",
            extra={
                "event": "qdrant_search",
                "substage": "qdrant_search",
                "latency_ms": t.ms(),
                "results_count": len(hits),
            },
        )
        log_event(
            logger,
            "qdrant_search",
            collection=coll,
            limit=limit,
            results_count=len(hits),
            filter_present=query_filter is not None,
        )
        out: list[dict[str, Any]] = []
        for h in hits:
            out.append(
                {
                    "id": str(h.id),
                    "score": float(h.score),
                    "payload": dict(h.payload or {}),
                }
            )
        return out

    def get_collection_metadata(self) -> dict[str, Any]:
        # Used to enforce EMBEDDING_MODEL lock against ingest-time metadata.
        c = self._client.get_collection(self._collection)
        return {
            "status": getattr(c, "status", None),
            "vectors_count": getattr(getattr(c, "points_count", None), "__int__", lambda: None)(),
            "config": getattr(c, "config", None),
        }
