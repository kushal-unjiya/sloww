"""HTTP entry for Cloud Run + Pub/Sub push subscriptions."""

from __future__ import annotations

import base64
import json
import logging

from fastapi import Body, FastAPI, Response

from data_loader.config import get_settings
from data_loader.jobs.repository import JobRepository
from data_loader.jobs.runner import run_job
from data_loader.shared.db import get_connection

logger = logging.getLogger("sloww.data_loader.http")

app = FastAPI(title="Sloww data-loader", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/pubsub/push")
def pubsub_push(payload: dict = Body(...)) -> Response:
    """Pub/Sub push JSON envelope: ``{ "message": { "data": "<base64>", ... }, ... }``."""
    msg = payload.get("message") or {}
    data_b64 = msg.get("data") or ""
    delivery_attempt = int(msg.get("deliveryAttempt") or 0)

    try:
        raw = base64.b64decode(data_b64).decode("utf-8")
        body = json.loads(raw)
    except Exception as exc:
        logger.warning("pubsub_bad_payload err=%s", exc)
        return Response(status_code=204)

    job_id = body.get("job_id")
    document_id = body.get("document_id")
    if not job_id or not document_id:
        logger.warning("pubsub_missing_ids")
        return Response(status_code=204)

    settings = get_settings()
    with get_connection() as conn:
        repo = JobRepository(conn)
        if repo.job_is_terminal(job_id=job_id, document_id=document_id):
            return Response(status_code=204)

        row = repo.try_claim_job_by_push(job_id=job_id, document_id=document_id)
        if row:
            logger.info(
                "push_job_claimed job_id=%s document_id=%s user_id=%s attempt=%s",
                job_id,
                document_id,
                row["user_id"],
                row["attempt_count"],
            )
            try:
                repo.heartbeat(str(job_id))
                run_job(repo, job_id=str(job_id), document_id=str(document_id))
                logger.info("push_job_completed job_id=%s document_id=%s", job_id, document_id)
            except Exception as exc:  # noqa: BLE001
                repo.mark_job_failed(
                    job_id=str(job_id),
                    document_id=str(document_id),
                    error_message=str(exc),
                )
                logger.exception("push_job_failed job_id=%s document_id=%s", job_id, document_id)
                return Response(status_code=500)
            return Response(status_code=200)

        meta = repo.get_ingestion_job_meta(job_id=job_id, document_id=document_id)
        if not meta:
            return Response(status_code=204)
        lb = meta.get("locked_by")
        if lb and lb != settings.worker_id:
            return Response(status_code=204)
        if delivery_attempt >= 8:
            logger.warning(
                "push_claim_exhausted job_id=%s document_id=%s attempts=%s",
                job_id,
                document_id,
                delivery_attempt,
            )
            return Response(status_code=204)
        return Response(status_code=503)


def run() -> None:
    from data_loader.shared.logging import configure_logging

    configure_logging()
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "data_loader.http_app:app",
        host="0.0.0.0",
        port=port,
        log_config=None,
    )
