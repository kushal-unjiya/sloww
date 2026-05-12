"""Extract plain text from PDF and DOCX bytes."""

from __future__ import annotations

import io
import re
from collections.abc import Iterator


def extract_text_pdf(content: bytes) -> Iterator[tuple[str, int | None]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            yield text, page_num


def extract_text_docx(content: bytes) -> Iterator[tuple[str, int | None]]:
    import docx

    document = docx.Document(io.BytesIO(content))
    parts: list[str] = []
    for para in document.paragraphs:
        t = (para.text or "").strip()
        if t:
            parts.append(t)
    full = "\n".join(parts)
    full = re.sub(r"\s+", " ", full).strip()
    if full:
        yield full, None


def extract_document_text(mime_type: str, content: bytes) -> Iterator[tuple[str, int | None]]:
    mt = (mime_type or "").lower()
    if "pdf" in mt:
        yield from extract_text_pdf(content)
    elif "wordprocessingml" in mt or "docx" in mt:
        yield from extract_text_docx(content)
    else:
        raise ValueError(f"unsupported mime type for ingestion: {mime_type!r}")
