"""Object download: Google Cloud Storage only."""

from data_loader.config import Settings
from data_loader.gcs_storage import download_bytes as gcs_download_bytes


def download_bytes(settings: Settings, storage_key: str) -> bytes:
    return gcs_download_bytes(settings, storage_key)
