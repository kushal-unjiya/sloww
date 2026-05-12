"""Download objects from GCS."""

from google.cloud import storage

from data_loader.config import Settings


def download_bytes(settings: Settings, storage_key: str) -> bytes:
    client = storage.Client(project=settings.gcs_project_id or None)
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(storage_key)
    return blob.download_as_bytes()
