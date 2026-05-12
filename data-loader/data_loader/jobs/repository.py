from typing import Any

from psycopg import Connection

from data_loader.config import get_settings
from data_loader.shared.status_codes import (
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_PROCESSED,
    STATUS_QUEUED,
)


class JobRepository:
    def __init__(self, conn: Connection):
        self._conn = conn
        self._schema = get_settings().db_schema

    def recover_stale_jobs(self) -> int:
        settings = get_settings()
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {self._schema}.ingestion_jobs
                SET status = %s, locked_by = NULL, locked_at = NULL, heartbeat_at = NULL,
                    updated_at = now(), next_retry_at = now()
                WHERE status = %s
                  AND heartbeat_at IS NOT NULL
                  AND heartbeat_at < now() - make_interval(secs => %s)
                """,
                (STATUS_QUEUED, STATUS_PROCESSING, settings.stale_job_threshold_seconds),
            )
            count = cur.rowcount
        self._conn.commit()
        return count

    def claim_one_queued_job(self) -> dict[str, Any] | None:
        settings = get_settings()
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                WITH picked AS (
                    SELECT j.id
                    FROM {self._schema}.ingestion_jobs j
                    INNER JOIN {self._schema}.documents d ON d.id = j.document_id AND d.is_deleted = false
                    WHERE (j.status = %s OR (j.status = %s AND j.locked_by IS NULL))
                      AND (j.next_retry_at IS NULL OR j.next_retry_at <= now())
                      AND (
                        SELECT COUNT(*) FROM {self._schema}.ingestion_jobs p
                        INNER JOIN {self._schema}.documents pd ON pd.id = p.document_id AND pd.is_deleted = false
                        WHERE p.user_id = j.user_id
                          AND p.status = %s
                          AND p.locked_by IS NOT NULL
                      ) < %s
                    ORDER BY j.created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE {self._schema}.ingestion_jobs j
                SET status = %s,
                    locked_by = %s,
                    locked_at = now(),
                    heartbeat_at = now(),
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                FROM picked
                WHERE j.id = picked.id
                RETURNING j.id, j.user_id, j.document_id, j.attempt_count
                """,
                (
                    STATUS_QUEUED,
                    STATUS_PROCESSING,
                    STATUS_PROCESSING,
                    settings.max_processing_per_user,
                    STATUS_PROCESSING,
                    settings.worker_id,
                ),
            )
            row = cur.fetchone()
        self._conn.commit()
        return row

    def try_claim_job_by_push(self, *, job_id: str, document_id: str) -> dict[str, Any] | None:
        """Claim a specific job (Pub/Sub push). Same eligibility as poller for QUEUED / unclaimed PROCESSING."""
        settings = get_settings()
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {self._schema}.ingestion_jobs j
                SET status = %s,
                    locked_by = %s,
                    locked_at = now(),
                    heartbeat_at = now(),
                    attempt_count = attempt_count + 1,
                    updated_at = now()
                WHERE j.id = %s
                  AND j.document_id = %s
                  AND (
                    j.status = %s
                    OR (j.status = %s AND j.locked_by IS NULL)
                  )
                  AND (j.next_retry_at IS NULL OR j.next_retry_at <= now())
                  AND (
                    SELECT COUNT(*) FROM {self._schema}.ingestion_jobs p
                    INNER JOIN {self._schema}.documents pd ON pd.id = p.document_id AND pd.is_deleted = false
                    WHERE p.user_id = j.user_id
                      AND p.status = %s
                      AND p.locked_by IS NOT NULL
                      AND p.id <> j.id
                  ) < %s
                RETURNING j.id, j.user_id, j.document_id, j.attempt_count
                """,
                (
                    STATUS_PROCESSING,
                    settings.worker_id,
                    job_id,
                    document_id,
                    STATUS_QUEUED,
                    STATUS_PROCESSING,
                    STATUS_PROCESSING,
                    settings.max_processing_per_user,
                ),
            )
            row = cur.fetchone()
        self._conn.commit()
        return dict(row) if row else None

    def job_is_terminal(self, *, job_id: str, document_id: str) -> bool:
        """True if job is already done (success or fail) — safe to ack Pub/Sub."""
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT status FROM {self._schema}.ingestion_jobs
                WHERE id = %s AND document_id = %s
                """,
                (job_id, document_id),
            )
            row = cur.fetchone()
        self._conn.commit()
        if not row:
            return True
        return int(row["status"]) in (STATUS_PROCESSED, STATUS_FAILED)

    def get_ingestion_job_meta(
        self, *, job_id: str, document_id: str
    ) -> dict[str, Any] | None:
        """status, locked_by, heartbeat_at for push-handler retry decisions."""
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT status, locked_by, heartbeat_at
                FROM {self._schema}.ingestion_jobs
                WHERE id = %s AND document_id = %s
                """,
                (job_id, document_id),
            )
            row = cur.fetchone()
        self._conn.commit()
        return dict(row) if row else None

    def heartbeat(self, job_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {self._schema}.ingestion_jobs
                SET heartbeat_at = now(), updated_at = now()
                WHERE id = %s AND status = %s
                """,
                (job_id, STATUS_PROCESSING),
            )
        self._conn.commit()

    def get_document_storage_key(self, document_id: str) -> str | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT storage_key FROM {self._schema}.documents
                WHERE id = %s AND is_deleted = false
                """,
                (document_id,),
            )
            row = cur.fetchone()
        self._conn.commit()
        return row["storage_key"] if row else None

    def mark_job_succeeded(
        self, *, job_id: str, document_id: str, chunk_count: int, total_tokens: int = 0
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {self._schema}.ingestion_jobs
                SET status = %s, updated_at = now(), completed_at = now(),
                    locked_by = NULL, locked_at = NULL
                WHERE id = %s
                """,
                (STATUS_PROCESSED, job_id),
            )
            cur.execute(
                f"""
                UPDATE {self._schema}.documents
                SET status = %s, chunk_count = %s, total_tokens = %s, processed_at = now(), updated_at = now()
                WHERE id = %s
                """,
                (STATUS_PROCESSED, chunk_count, total_tokens, document_id),
            )
        self._conn.commit()

    def get_document_for_ingestion(self, document_id: str) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                  d.id AS id,
                  d.storage_key AS storage_key,
                  d.mime_type AS mime_type,
                  d.title AS title,
                  d.original_filename AS original_filename,
                  pd.project_id AS project_id
                FROM {self._schema}.documents d
                INNER JOIN {self._schema}.project_documents pd ON pd.document_id = d.id
                WHERE d.id = %s AND d.is_deleted = false
                LIMIT 1
                """,
                (document_id,),
            )
            row = cur.fetchone()
        self._conn.commit()
        return dict(row) if row else None

    def mark_job_failed(self, *, job_id: str, document_id: str, error_message: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {self._schema}.ingestion_jobs
                SET status = %s, updated_at = now(), completed_at = now(),
                    error_message = %s, locked_by = NULL, locked_at = NULL
                WHERE id = %s
                """,
                (STATUS_FAILED, error_message[:2000], job_id),
            )
            cur.execute(
                f"""
                UPDATE {self._schema}.documents
                SET status = %s, updated_at = now()
                WHERE id = %s
                """,
                (STATUS_FAILED, document_id),
            )
        self._conn.commit()
