"""Chat persistence (conversations, messages, retrieval runs, citations)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.auth.deps import get_settings_dep
from api.config import Settings
from api.shared.chat_codes import MESSAGE_STATUS_COMPLETE
from api.shared.db import get_session


@dataclass(frozen=True)
class ChatRepository:
    db: Session
    settings: Settings

    @property
    def _schema(self) -> str:
        return self.settings.db_schema

    def create_conversation(
        self,
        *,
        user_id: UUID,
        project_id: UUID,
        title: str = "Chat",
    ) -> UUID:
        row = self.db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.conversations
                  (id, user_id, project_id, created_by_user_id, title, status, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, :project_id, :user_id, :title, 1, now(), now())
                RETURNING id
                """
            ),
            {
                "user_id": user_id,
                "project_id": project_id,
                "title": title[:512],
            },
        ).one()
        return row[0]

    def get_conversation(
        self, *, user_id: UUID, conversation_id: UUID
    ) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                f"""
                SELECT id, title, created_at, updated_at, last_message_at
                FROM {self._schema}.conversations
                WHERE id = :conversation_id AND user_id = :user_id
                """
            ),
            {"conversation_id": conversation_id, "user_id": user_id},
        ).mappings().first()
        return dict(row) if row else None

    def list_conversations(self, *, user_id: UUID, project_id: UUID) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text(
                f"""
                SELECT id, title, created_at, updated_at, last_message_at
                FROM {self._schema}.conversations
                WHERE user_id = :user_id AND project_id = :project_id
                ORDER BY COALESCE(last_message_at, updated_at) DESC
                """
            ),
            {"user_id": user_id, "project_id": project_id},
        ).mappings().all()
        return [dict(r) for r in rows]

    def list_messages(self, *, conversation_id: UUID, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text(
                f"""
                SELECT id, role, content, status, metadata, created_at
                FROM {self._schema}.messages
                WHERE conversation_id = :cid
                ORDER BY created_at ASC
                LIMIT :lim
                """
            ),
            {"cid": conversation_id, "lim": limit},
        ).mappings().all()
        return [dict(r) for r in rows]

    def insert_message(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID | None,
        role: int,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> UUID:
        meta_json = json.dumps(metadata or {})
        row = self.db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.messages
                  (id, conversation_id, user_id, role, content, status, metadata, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :conversation_id, :user_id, :role, :content, :status, CAST(:metadata AS jsonb), now(), now())
                RETURNING id
                """
            ),
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "status": MESSAGE_STATUS_COMPLETE,
                "metadata": meta_json,
            },
        ).one()
        self.db.execute(
            text(
                f"""
                UPDATE {self._schema}.conversations
                SET last_message_at = now(), updated_at = now()
                WHERE id = :cid
                """
            ),
            {"cid": conversation_id},
        )
        return row[0]

    def insert_retrieval_run(
        self,
        *,
        message_id: UUID,
        user_id: UUID,
        top_k: int,
        results: list[dict[str, Any]],
    ) -> UUID:
        row = self.db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.retrieval_runs
                  (id, message_id, user_id, top_k, results, created_at)
                VALUES
                  (gen_random_uuid(), :message_id, :user_id, :top_k, CAST(:results AS jsonb), now())
                RETURNING id
                """
            ),
            {
                "message_id": message_id,
                "user_id": user_id,
                "top_k": top_k,
                "results": json.dumps(results),
            },
        ).one()
        return row[0]

    def insert_citations(
        self,
        *,
        message_id: UUID,
        retrieval_run_id: UUID,
        citations: list[dict[str, Any]],
    ) -> None:
        for c in citations:
            excerpt = c.get("excerpt_80") or ""
            doc_id = c.get("document_id")
            doc_uuid = None
            if doc_id:
                try:
                    doc_uuid = UUID(str(doc_id))
                except (ValueError, TypeError):
                    doc_uuid = None
            self.db.execute(
                text(
                    f"""
                    INSERT INTO {self._schema}.citations
                      (id, message_id, retrieval_run_id, chunk_id, document_id, qdrant_point_id,
                       citation_order, excerpt_text, page_number, section_path, score, rerank_score, created_at)
                    VALUES
                      (gen_random_uuid(), :message_id, :retrieval_run_id, :chunk_id, :document_id, :qdrant_point_id,
                       :citation_order, :excerpt_text, :page_number, :section_path, :score, :rerank_score, now())
                    """
                ),
                {
                    "message_id": message_id,
                    "retrieval_run_id": retrieval_run_id,
                    "chunk_id": str(c.get("chunk_id", "")),
                    "document_id": doc_uuid,
                    "qdrant_point_id": c.get("qdrant_point_id"),
                    "citation_order": int(c.get("ref_num", 0)),
                    "excerpt_text": excerpt[:20000],
                    "page_number": c.get("page"),
                    "section_path": None,
                    "score": c.get("score"),
                    "rerank_score": c.get("rerank_score"),
                },
            )


def get_chat_repo(
    db: Session = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> ChatRepository:
    return ChatRepository(db=db, settings=settings)


__all__ = ["ChatRepository", "get_chat_repo"]
