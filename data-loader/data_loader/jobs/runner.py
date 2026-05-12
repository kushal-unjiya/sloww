from __future__ import annotations

from uuid import uuid4

from data_loader.config import get_settings
from data_loader.embeddings import embed_text
from data_loader.extract import extract_document_text
from data_loader.jobs.repository import JobRepository
from data_loader.parsing import iter_chunks_for_document
from data_loader.qdrant_ingest import (
    collection_name_for_project,
    delete_document_points,
    ensure_collection,
    upsert_chunks,
)
from data_loader.storage import download_bytes


def run_job(repo: JobRepository, *, job_id: str, document_id: str) -> None:
    settings = get_settings()
    row = repo.get_document_for_ingestion(document_id)
    if not row:
        raise RuntimeError(f"document {document_id} not found or not linked to a project")

    content = download_bytes(settings, row["storage_key"])
    if not content:
        raise RuntimeError("empty object received from storage")

    parts: list[tuple[str, int | None]] = list(extract_document_text(row["mime_type"], content))
    if not parts:
        raise RuntimeError("no extractable text from document")

    chunk_tuples = list(
        iter_chunks_for_document(
            parts,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
    )
    if not chunk_tuples:
        raise RuntimeError("no chunks after segmentation")

    project_id = row["project_id"]
    notebook_id = str(project_id)
    collection = collection_name_for_project(project_id, settings)

    ensure_collection(settings, collection, settings.embedding_vector_size)

    vectors: list[list[float]] = []
    for text, _page in chunk_tuples:
        vec = embed_text(text, settings)
        if len(vec) != settings.embedding_vector_size:
            raise RuntimeError(
                f"embedding dim {len(vec)} != configured EMBEDDING_VECTOR_SIZE={settings.embedding_vector_size}"
            )
        vectors.append(vec)

    triples: list[tuple[str, int | None, str]] = [
        (text, page, str(uuid4())) for text, page in chunk_tuples
    ]

    delete_document_points(settings, collection_name=collection, document_id=document_id)

    original_filename = row["original_filename"] or row["title"] or "document"

    upsert_chunks(
        settings,
        collection_name=collection,
        project_id=project_id,
        document_id=document_id,
        original_filename=original_filename,
        notebook_id=notebook_id,
        chunks=triples,
        embed=vectors,
    )

    total_chars = sum(len(t[0]) for t in chunk_tuples)
    total_tokens = max(1, total_chars // 4)

    repo.mark_job_succeeded(
        job_id=job_id,
        document_id=document_id,
        chunk_count=len(triples),
        total_tokens=total_tokens,
    )
