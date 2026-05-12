"""Qdrant: one collection per project, payload holds citation metadata + raw_text."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from data_loader.config import Settings


def collection_name_for_project(project_id: UUID | str, settings: Settings) -> str:
    return f"{settings.qdrant_collection_prefix}{project_id}"


def _client(settings: Settings) -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)


def ensure_collection(settings: Settings, name: str, vector_size: int) -> None:
    client = _client(settings)
    cols = client.get_collections().collections
    existing = {c.name for c in cols}
    if name in existing:
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def delete_document_points(
    settings: Settings,
    *,
    collection_name: str,
    document_id: UUID | str,
) -> None:
    client = _client(settings)
    doc_str = str(document_id)
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=doc_str))]
                )
            ),
        )
    except Exception:
        # collection may not exist yet
        pass


def upsert_chunks(
    settings: Settings,
    *,
    collection_name: str,
    project_id: UUID | str,
    document_id: UUID | str,
    original_filename: str,
    notebook_id: str,
    chunks: list[tuple[str, int | None, str]],
    embed: list[list[float]],
) -> int:
    """chunks: (raw_text, page_number, chunk_id_uuid_str); embed aligned."""
    if len(chunks) != len(embed):
        raise ValueError("chunks and embed length mismatch")
    client = _client(settings)
    points: list[PointStruct] = []
    for idx, ((raw_text, page_number, chunk_id), vector) in enumerate(zip(chunks, embed, strict=True)):
        payload: dict[str, Any] = {
            "notebook_id": notebook_id,
            "project_id": str(project_id),
            "document_id": str(document_id),
            "doc_id": str(document_id),
            "original_filename": original_filename,
            "chunk_id": chunk_id,
            "chunk_index": idx,
            "raw_text": raw_text,
            "page_number": page_number,
        }
        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=vector,
                payload=payload,
            )
        )
    if points:
        client.upsert(collection_name=collection_name, points=points)
    return len(points)
