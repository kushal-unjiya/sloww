from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


class LatestJobOut(BaseModel):
    status: int | None
    error_message: str | None = None
    updated_at: datetime | None = None


class DocumentOut(BaseModel):
    id: str
    title: str
    source_type: str
    storage_key: str
    original_filename: str
    mime_type: str
    byte_size: int
    checksum_sha256: str
    status: int
    chunk_count: int | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    latest_job: LatestJobOut | None


class DocumentListOut(BaseModel):
    items: list[DocumentOut]


class RegisterDocumentBody(BaseModel):
    storage_key: str = Field(min_length=8, max_length=1024)
    filename: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=256)
    byte_size: int = Field(gt=0)
    checksum_sha256: str = Field(min_length=64, max_length=64)
    title: str | None = Field(default=None, max_length=2048)
    project_id: UUID = Field()  # REQUIRED

    @field_validator("checksum_sha256")
    @classmethod
    def hex_lower(cls, v: str) -> str:
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("checksum_sha256 must be 64 hex characters")
        return v.lower()


class RegisterDocumentOut(BaseModel):
    id: str
    status: int
    job_id: str


class PatchDocumentBody(BaseModel):
    title: str = Field(min_length=1, max_length=2048)
