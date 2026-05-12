import asyncio
import hashlib
from typing import NamedTuple
from uuid import UUID

from fastapi import HTTPException, UploadFile

from api.config import Settings
from api.shared.logging import get_logger
from api.uploads.responses import PresignBody, PresignResponse
from api.uploads.storage import (
    build_storage_key,
    delete_object,
    presign_put_object,
    put_object_bytes,
    sanitize_filename,
)

logger = get_logger("sloww.uploads")


class UploadedBlob(NamedTuple):
    storage_key: str
    filename: str
    mime_type: str
    byte_size: int
    checksum_sha256: str


class UploadService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_presigned_put(self, body: PresignBody) -> PresignResponse:
        if body.byte_size > self._settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file too large (max {self._settings.max_upload_bytes} bytes)",
            )
        storage_key = build_storage_key(str(body.project_id), body.filename)
        logger.debug(
            "presign_requested project_id=%s filename=%s mime_type=%s byte_size=%s storage_key=%s",
            body.project_id,
            body.filename,
            body.mime_type,
            body.byte_size,
            storage_key,
        )
        url = presign_put_object(
            self._settings,
            storage_key,
            body.mime_type,
            self._settings.presign_expires_seconds,
        )
        logger.info("presign_issued project_id=%s storage_key=%s", body.project_id, storage_key)
        return PresignResponse(upload_url=url, storage_key=storage_key)

    async def upload_object_for_project(
        self,
        project_id: UUID,
        file: UploadFile,
    ) -> UploadedBlob:
        content = await file.read()
        if len(content) > self._settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"file too large (max {self._settings.max_upload_bytes} bytes)",
            )
        raw_name = file.filename or "upload"
        filename = sanitize_filename(raw_name)
        mime_type = file.content_type or "application/octet-stream"
        storage_key = build_storage_key(str(project_id), raw_name)
        checksum = hashlib.sha256(content).hexdigest()
        logger.info(
            "upload_object_start project_id=%s storage_key=%s byte_size=%s",
            project_id,
            storage_key,
            len(content),
        )
        await asyncio.to_thread(
            put_object_bytes,
            self._settings,
            storage_key,
            content,
            mime_type,
        )
        logger.info("upload_object_done project_id=%s storage_key=%s", project_id, storage_key)
        return UploadedBlob(
            storage_key=storage_key,
            filename=filename,
            mime_type=mime_type,
            byte_size=len(content),
            checksum_sha256=checksum,
        )

    def delete_object_best_effort(self, storage_key: str) -> None:
        """Remove object after failed DB registration (upload compensation)."""
        try:
            delete_object(self._settings, storage_key)
            logger.info("upload_compensation_deleted storage_key=%s", storage_key)
        except Exception:
            logger.exception("upload_compensation_delete_failed storage_key=%s", storage_key)
