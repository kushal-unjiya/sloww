from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Service-local only; Docker Compose uses compose.env separately.
    model_config = SettingsConfigDict(env_file=(".env",), extra="ignore")

    database_url: str
    db_schema: str = "sloww_ai"

    ingest_mode: Literal["poll", "push"] = Field(
        default="poll",
        validation_alias=AliasChoices("INGEST_MODE"),
    )

    gcs_bucket_name: str = Field(validation_alias=AliasChoices("GCS_BUCKET_NAME"))
    gcs_project_id: str | None = Field(default=None, validation_alias=AliasChoices("GCS_PROJECT_ID"))

    worker_id: str = "data-loader-1"
    poll_interval_seconds: float = 2.0
    max_processing_per_user: int = 5
    stale_job_threshold_seconds: int = 90
    heartbeat_interval_seconds: int = 30

    qdrant_url: str = Field(default="http://localhost:6333", validation_alias=AliasChoices("QDRANT_URL"))
    qdrant_api_key: str | None = Field(default=None, validation_alias=AliasChoices("QDRANT_API_KEY"))
    qdrant_collection_prefix: str = Field(
        default="proj_",
        validation_alias=AliasChoices("QDRANT_COLLECTION_PREFIX"),
    )

    embedding_model: str = Field(
        default="nvidia/llama-nemotron-embed-vl-1b-v2",
        validation_alias=AliasChoices("EMBEDDING_MODEL"),
    )
    embedding_vector_size: int = Field(default=2048, validation_alias=AliasChoices("EMBEDDING_VECTOR_SIZE"))
    nvidia_nim_api_key: str | None = Field(default=None, validation_alias=AliasChoices("NVIDIA_NIM_API_KEY"))
    nvidia_nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        validation_alias=AliasChoices("NVIDIA_NIM_BASE_URL"),
    )
    openrouter_api_key: str | None = Field(default=None, validation_alias=AliasChoices("OPENROUTER_API_KEY"))
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("OPENROUTER_BASE_URL"),
    )
    hf_api_key: str | None = Field(default=None, validation_alias=AliasChoices("HF_API_KEY"))

    chunk_size: int = Field(default=800, validation_alias=AliasChoices("INGEST_CHUNK_SIZE"))
    chunk_overlap: int = Field(default=120, validation_alias=AliasChoices("INGEST_CHUNK_OVERLAP"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
