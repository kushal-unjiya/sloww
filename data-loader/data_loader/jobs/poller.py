import logging
import time
from uuid import UUID

from data_loader.config import get_settings
from data_loader.jobs.repository import JobRepository
from data_loader.jobs.runner import run_job
from data_loader.shared.db import get_connection

logger = logging.getLogger("sloww.data_loader")


def _uuid_to_str(value: UUID | str) -> str:
    return str(value)


def run_worker_forever() -> None:
    settings = get_settings()
    logger.info(
        "worker_started worker_id=%s poll_interval=%s",
        settings.worker_id,
        settings.poll_interval_seconds,
    )
    with get_connection() as conn:
        repo = JobRepository(conn)
        last_recovery = 0.0
        while True:
            now = time.time()
            if now - last_recovery >= settings.heartbeat_interval_seconds:
                recovered = repo.recover_stale_jobs()
                if recovered:
                    logger.warning("stale_jobs_recovered count=%s", recovered)
                last_recovery = now

            job = repo.claim_one_queued_job()
            if not job:
                time.sleep(settings.poll_interval_seconds)
                continue

            job_id = _uuid_to_str(job["id"])
            document_id = _uuid_to_str(job["document_id"])
            user_id = _uuid_to_str(job["user_id"])
            logger.info(
                "job_claimed job_id=%s document_id=%s user_id=%s attempt=%s",
                job_id,
                document_id,
                user_id,
                job["attempt_count"],
            )
            try:
                repo.heartbeat(job_id)
                run_job(repo, job_id=job_id, document_id=document_id)
                logger.info(
                    "job_completed job_id=%s document_id=%s user_id=%s",
                    job_id,
                    document_id,
                    user_id,
                )
            except Exception as exc:
                repo.mark_job_failed(job_id=job_id, document_id=document_id, error_message=str(exc))
                logger.exception(
                    "job_failed job_id=%s document_id=%s user_id=%s error=%s",
                    job_id,
                    document_id,
                    user_id,
                    exc,
                )
