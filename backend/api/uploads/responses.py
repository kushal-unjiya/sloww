from uuid import UUID

from pydantic import BaseModel, Field


class PresignBody(BaseModel):
    project_id: UUID
    filename: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=256)
    byte_size: int = Field(gt=0)


class PresignResponse(BaseModel):
    upload_url: str
    storage_key: str


class UploadObjectOut(BaseModel):
    """Server-side upload to GCS and DB row in one request when ``project_id`` is sent."""

    storage_key: str
    filename: str
    mime_type: str
    byte_size: int
    checksum_sha256: str
    document_id: str
    status: int
    job_id: str
