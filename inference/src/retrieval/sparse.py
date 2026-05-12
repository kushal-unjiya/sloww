from __future__ import annotations

import re

from rank_bm25 import BM25Okapi
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.config import get_settings
from src.graph.state import Chunk
from src.shared.db import qualify_table
from src.shared.logging import get_logger, timer

logger = get_logger("sloww.inference.retrieval.sparse")

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class BM25Retriever:
    def __init__(self, *, engine: AsyncEngine, top_k: int) -> None:
        self._engine = engine
        self._top_k = top_k
        self._schema = get_settings().db_schema
        self._disabled_reason: str | None = None

    async def __call__(self, *, notebook_id: str, query: str) -> list[Chunk]:
        t = timer()
        if self._disabled_reason is not None:
            logger.debug(
                "bm25_skipped_disabled",
                extra={
                    "event": "bm25_skipped_disabled",
                    "reason": self._disabled_reason,
                },
            )
            return []

        # ILIKE pre-filter; BM25 in-process.
        table = qualify_table(schema=self._schema, table="chunks_metadata")
        q_tokens = [
            tok
            for tok in _TOKEN_RE.findall(query.lower())
            if len(tok) >= 3
        ][:10]
        if not q_tokens:
            q_tokens = _TOKEN_RE.findall(query.lower())[:5]

        like_clauses: list[str] = []
        params: dict[str, object] = {"notebook_id": notebook_id}
        for idx, tok in enumerate(q_tokens):
            key = f"term_{idx}"
            like_clauses.append(f"LOWER(raw_text) LIKE :{key}")
            params[key] = f"%{tok}%"

        prefilter = " OR ".join(like_clauses) if like_clauses else "TRUE"
        sql = text(
            f"""
            SELECT
              chunk_id,
              doc_id,
              notebook_id,
              page,
              char_offset,
              raw_text
            FROM {table}
            WHERE notebook_id = :notebook_id
              AND ({prefilter})
            LIMIT 500
            """
        )

        try:
            async with self._engine.connect() as conn:
                rows = (await conn.execute(sql, params)).mappings().all()
        except ProgrammingError as exc:
            msg = str(exc)
            if "UndefinedTableError" in msg or "does not exist" in msg:
                self._disabled_reason = f"missing table {table}"
                logger.warning(
                    "bm25_disabled_missing_table",
                    extra={
                        "event": "bm25_disabled_missing_table",
                        "table": table,
                        "latency_ms": t.ms(),
                    },
                )
                return []
            raise

        if not rows:
            logger.info(
                "bm25_done",
                extra={
                    "event": "bm25_done",
                    "substage": "bm25_retrieval",
                    "latency_ms": t.ms(),
                    "results_count": 0,
                    "query_token_count": len(_TOKEN_RE.findall(query.lower())),
                },
            )
            return []

        docs = [str(r["raw_text"]) for r in rows]
        tokenized = [_TOKEN_RE.findall(d.lower()) for d in docs]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(q_tokens)

        ranked = sorted(list(enumerate(scores)), key=lambda x: x[1], reverse=True)[: self._top_k]
        out: list[Chunk] = []
        for idx, score in ranked:
            r = rows[idx]
            out.append(
                Chunk(
                    chunk_id=str(r["chunk_id"]),
                    doc_id=str(r["doc_id"]),
                    notebook_id=str(r["notebook_id"]),
                    page=r.get("page"),
                    char_offset=r.get("char_offset"),
                    raw_text=str(r["raw_text"]),
                    score=float(score),
                    source="sparse",
                )
            )

        logger.info(
            "bm25_done",
            extra={
                "event": "bm25_done",
                "substage": "bm25_retrieval",
                "latency_ms": t.ms(),
                "results_count": len(out),
                "query_token_count": len(q_tokens),
            },
        )
        return out
