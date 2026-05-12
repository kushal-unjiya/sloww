"""Google Cloud Storage: presigned PUT, upload, delete (object path = storage_key)."""

import uuid
from datetime import timedelta
from pathlib import PurePosixPath

from google.cloud import storage

from api.config import Settings


def sanitize_filename(name: str) -> str:
    base = PurePosixPath(name).name
    if not base or base in (".", ".."):
        base = "upload"
    return base[:200]


def build_storage_key(project_id: str, filename: str) -> str:
    """Objects live in one virtual folder per project: ``{project_id}/{uuid}_{filename}``."""
    safe = sanitize_filename(filename)
    return f"{project_id}/{uuid.uuid4()}_{safe}"


def _bucket(settings: Settings) -> storage.Bucket:
    client = storage.Client(project=settings.gcs_project_id or None)
    return client.bucket(settings.gcs_bucket_name)


def presign_put_object(
    settings: Settings,
    storage_key: str,
    mime_type: str,
    expires_in: int,
) -> str:
    blob = _bucket(settings).blob(storage_key)
    return blob.generate_signed_url(
        version="v4",
        expiration=timedelta(seconds=expires_in),
        method="PUT",
        content_type=mime_type,
    )


def put_object_bytes(
    settings: Settings,
    storage_key: str,
    body: bytes,
    content_type: str,
) -> None:
    blob = _bucket(settings).blob(storage_key)
    blob.upload_from_string(body, content_type=content_type)


def delete_object(settings: Settings, storage_key: str) -> None:
    """Remove one object (no-op if already missing)."""
    from google.cloud.exceptions import NotFound

    blob = _bucket(settings).blob(storage_key)
    try:
        blob.delete()
    except NotFound:
        pass
