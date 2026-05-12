"""Publish ingestion messages to GCP Pub/Sub (optional)."""

from __future__ import annotations

import json
import logging
from uuid import UUID

logger = logging.getLogger("sloww.pubsub")

_publisher = None


def _get_publisher():
    global _publisher
    if _publisher is None:
        from google.cloud import pubsub_v1

        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_ingestion_job(
    *,
    topic_full: str | None,
    enabled: bool,
    project_id: UUID,
    document_id: str,
    job_id: str,
    storage_key: str | None = None,
) -> None:
    """Best-effort publish. On failure, ingestion still runs via Postgres poller."""
    if not enabled or not topic_full:
        return
    payload = {
        "job_id": job_id,
        "document_id": document_id,
        "project_id": str(project_id),
        "storage_key": storage_key or "",
    }
    data = json.dumps(payload).encode("utf-8")
    try:
        future = _get_publisher().publish(topic_full, data)
        future.result(timeout=15.0)
        logger.info(
            "pubsub_ingestion_published topic=%s document_id=%s job_id=%s",
            topic_full,
            document_id,
            job_id,
        )
    except Exception:
        logger.exception(
            "pubsub_ingestion_publish_failed topic=%s document_id=%s",
            topic_full,
            document_id,
        )
