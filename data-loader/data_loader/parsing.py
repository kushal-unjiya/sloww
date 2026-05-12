"""Chunk text into overlapping segments."""

from __future__ import annotations

from collections.abc import Iterator


def chunk_segments(
    text: str,
    *,
    page_number: int | None,
    chunk_size: int,
    chunk_overlap: int,
) -> Iterator[tuple[str, int | None]]:
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 4)
    if not text:
        return
    start = 0
    idx = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        piece = text[start:end].strip()
        if piece:
            yield piece, page_number
            idx += 1
        if end >= n:
            break
        start = end - chunk_overlap


def iter_chunks_for_document(
    parts: list[tuple[str, int | None]],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> Iterator[tuple[str, int | None]]:
    for text, page in parts:
        yield from chunk_segments(
            text,
            page_number=page,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
