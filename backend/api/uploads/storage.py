"""Object storage: Google Cloud Storage only."""

from api.config import Settings
from api.uploads import gcs_client


def build_storage_key(project_id: str, filename: str) -> str:
    return gcs_client.build_storage_key(project_id, filename)


def sanitize_filename(name: str) -> str:
    return gcs_client.sanitize_filename(name)


def presign_put_object(
    settings: Settings,
    storage_key: str,
    mime_type: str,
    expires_in: int,
) -> str:
    return gcs_client.presign_put_object(settings, storage_key, mime_type, expires_in)


def put_object_bytes(
    settings: Settings,
    storage_key: str,
    body: bytes,
    content_type: str,
) -> None:
    gcs_client.put_object_bytes(settings, storage_key, body, content_type)


def delete_object(settings: Settings, storage_key: str) -> None:
    gcs_client.delete_object(settings, storage_key)
