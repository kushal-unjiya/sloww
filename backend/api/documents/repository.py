from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.config import Settings
from api.shared.status_codes import (
    STATUS_PROCESSING,
    STATUS_QUEUED,
    STATUS_UPLOADED,
)

_DOC_SELECT = """
SELECT
  d.id,
  d.user_id,
  d.title,
  d.source_type,
  d.storage_key,
  d.original_filename,
  d.mime_type,
  d.byte_size,
  d.checksum_sha256,
  d.status AS document_status,
  d.chunk_count,
  d.created_at,
  d.updated_at,
  d.processed_at,
  j.status AS job_status,
  j.error_message AS job_error_message,
  j.updated_at AS job_updated_at
FROM {schema}.documents d
LEFT JOIN LATERAL (
  SELECT status, error_message, updated_at
  FROM {schema}.ingestion_jobs
  WHERE document_id = d.id
  ORDER BY created_at DESC
  LIMIT 1
) j ON true
"""


class DocumentRepository:
    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._schema = settings.db_schema

    @property
    def session(self) -> Session:
        return self._db

    def _select_sql(self) -> str:
        return _DOC_SELECT.format(schema=self._schema)

    def fetch_row_for_user(
        self, user_id: UUID, document_id: UUID
    ) -> dict[str, Any] | None:
        q = (
            self._select_sql()
            + " WHERE d.is_deleted = false AND d.id = :doc_id AND d.user_id = :uid"
        )
        row = self._db.execute(
            text(q),
            {"doc_id": document_id, "uid": user_id},
        ).mappings().first()
        return dict(row) if row else None

    def list_rows_for_user(
        self, user_id: UUID, project_id: UUID | None = None
    ) -> list[dict[str, Any]]:
        if project_id is not None:
            q = (
                self._select_sql()
                + """
                INNER JOIN {schema}.project_documents pd
                  ON pd.document_id = d.id AND pd.project_id = :project_id
                WHERE d.is_deleted = false AND d.user_id = :uid
                ORDER BY d.created_at DESC
                """.format(schema=self._schema)
            )
            rows = self._db.execute(
                text(q), {"uid": user_id, "project_id": project_id}
            ).mappings().all()
        else:
            q = (
                self._select_sql()
                + " WHERE d.is_deleted = false AND d.user_id = :uid ORDER BY d.created_at DESC"
            )
            rows = self._db.execute(text(q), {"uid": user_id}).mappings().all()
        return [dict(r) for r in rows]

    def insert_document(
        self,
        *,
        user_id: UUID,
        title: str,
        storage_key: str,
        original_filename: str,
        mime_type: str,
        byte_size: int,
        checksum: str,
        status: int = STATUS_UPLOADED,
    ) -> dict[str, Any]:
        row = self._db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.documents
                  (id, user_id, created_by_user_id, title, source_type, storage_key,
                   original_filename, mime_type, byte_size, checksum_sha256, status,
                   chunk_count, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, :user_id, :title, 'upload', :storage_key,
                   :original_filename, :mime_type, :byte_size, :checksum, :status,
                   NULL, now(), now())
                RETURNING id, status
                """
            ),
            {
                "user_id": user_id,
                "title": title,
                "storage_key": storage_key,
                "original_filename": original_filename,
                "mime_type": mime_type,
                "byte_size": byte_size,
                "checksum": checksum,
                "status": status,
            },
        ).mappings().one()
        return dict(row)

    def count_processing_jobs_for_user(self, *, user_id: UUID) -> int:
        count = self._db.execute(
            text(
                f"""
                SELECT COUNT(*)::int AS c
                FROM {self._schema}.ingestion_jobs
                WHERE user_id = :user_id
                  AND status = :status
                  AND locked_by IS NOT NULL
                """
            ),
            {"user_id": user_id, "status": STATUS_PROCESSING},
        ).scalar_one()
        return int(count)

    def insert_ingestion_job(
        self, *, user_id: UUID, document_id: UUID, status: int = STATUS_QUEUED
    ) -> UUID:
        row_id = self._db.execute(
            text(
                f"""
                INSERT INTO {self._schema}.ingestion_jobs
                  (id, user_id, document_id, status, attempt_count, created_at, updated_at,
                   next_retry_at)
                VALUES
                  (gen_random_uuid(), :user_id, :doc_id, :status, 0, now(), now(), now())
                RETURNING id
                """
            ),
            {"user_id": user_id, "doc_id": document_id, "status": status},
        ).scalar_one()
        return UUID(str(row_id))

    def update_title(
        self, *, user_id: UUID, document_id: UUID, title: str
    ) -> None:
        self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.documents
                SET title = :title, updated_at = now()
                WHERE id = :doc_id AND user_id = :user_id
                """
            ),
            {"title": title, "doc_id": document_id, "user_id": user_id},
        )

    def soft_delete_document(self, user_id: UUID, doc_id: UUID) -> bool:
        """Remove satellite rows, mark document row deleted (keeps tombstone row)."""
        self._db.execute(
            text(
                f"DELETE FROM {self._schema}.processing_artifacts "
                "WHERE document_id = :doc_id"
            ),
            {"doc_id": doc_id},
        )
        self._db.execute(
            text(
                f"DELETE FROM {self._schema}.ingestion_jobs "
                "WHERE document_id = :doc_id"
            ),
            {"doc_id": doc_id},
        )
        res = self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.documents
                SET is_deleted = true,
                    deleted_at = now(),
                    updated_at = now()
                WHERE id = :doc_id AND user_id = :user_id AND is_deleted = false
                """
            ),
            {"doc_id": doc_id, "user_id": user_id},
        )
        return res.rowcount > 0

    def reset_document_for_reprocess(self, *, user_id: UUID, document_id: UUID) -> None:
        self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.documents
                SET status = :status, updated_at = now(), processed_at = NULL, chunk_count = NULL
                WHERE id = :doc_id AND user_id = :user_id
                """
            ),
            {
                "doc_id": document_id,
                "user_id": user_id,
                "status": STATUS_QUEUED,
            },
        )

    def update_document_status(
        self, *, user_id: UUID, document_id: UUID, status: int
    ) -> None:
        self._db.execute(
            text(
                f"""
                UPDATE {self._schema}.documents
                SET status = :status, updated_at = now()
                WHERE id = :doc_id AND user_id = :user_id
                """
            ),
            {"doc_id": document_id, "user_id": user_id, "status": status},
        )
