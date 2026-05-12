from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Service-local only; Docker Compose uses compose.env separately.
        env_file=(".env",),
        extra="ignore",
    )

    # Service identity
    service_name: str = "inference"  # SERVICE_NAME
    environment: str = "development"  # ENVIRONMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"  # LOG_LEVEL
    log_format: Literal["json", "pretty"] = "json"  # LOG_FORMAT

    # Database (backend-owned schema/migrations)
    database_url: str  # DATABASE_URL (sqlalchemy+asyncpg)
    db_schema: str = "sloww_ai"  # DB_SCHEMA

    # Vector store
    qdrant_url: str  # QDRANT_URL
    qdrant_api_key: str | None = None  # QDRANT_API_KEY
    qdrant_collection: str = "documents"  # QDRANT_COLLECTION (legacy default; per-project uses prefix+notebook_id)
    qdrant_collection_prefix: str = Field(default="proj_", validation_alias="QDRANT_COLLECTION_PREFIX")

    # Embedding invariants and provider chain
    embedding_model: str = Field(
        default="nvidia/llama-nemotron-embed-vl-1b-v2",
        validation_alias=AliasChoices("EMBEDDING_MODEL"),
    )
    nvidia_nim_api_key: str | None = Field(default=None, validation_alias="NVIDIA_NIM_API_KEY")
    nvidia_nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        validation_alias="NVIDIA_NIM_BASE_URL",
    )
    openrouter_api_key: str | None = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias="OPENROUTER_BASE_URL",
    )
    hf_api_key: str | None = Field(default=None, validation_alias="HF_API_KEY")

    # LLM provider chain (Groq -> OpenRouter -> Google)
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    google_ai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_AI_API_KEY", "GOOGLE_API_KEY"),
    )

    llm_primary_model: str = Field(default="groq:llama-3.1-8b-instant", validation_alias="LLM_PRIMARY_MODEL")
    llm_openrouter_model: str = Field(
        default="openrouter:meta-llama/llama-3.1-8b-instruct",
        validation_alias="LLM_OPENROUTER_MODEL",
    )
    llm_google_model: str = Field(
        default="google:gemma-4-26b-a4b-it",
        validation_alias="LLM_GOOGLE_MODEL",
    )
    # Comma-separated provider order, e.g. ``google`` (Google-only dev) or ``groq,openrouter,google``.
    llm_provider_chain: str = Field(
        default="groq,openrouter,google",
        validation_alias="LLM_PROVIDER_CHAIN",
    )
    # Optional faster chain for intent/HyDE/coverage/planner (same provider names). When unset, ``llm_provider_chain`` is used.
    # Example: ``LLM_ROUTER_CHAIN=groq`` + ``LLM_PROVIDER_CHAIN=google`` → routing on Groq (≈sub-second), answers on Gemma/Gemini.
    llm_router_chain: str | None = Field(default=None, validation_alias="LLM_ROUTER_CHAIN")
    # When router uses ``google``, pick a fast model (e.g. ``google:gemini-flash-latest``); falls back to ``LLM_GOOGLE_MODEL``.
    llm_router_google_model: str | None = Field(default=None, validation_alias="LLM_ROUTER_GOOGLE_MODEL")

    # Cross-encoder (loaded once at startup)
    cross_encoder_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        validation_alias="CROSS_ENCODER_MODEL",
    )

    # Graph tuning
    loop_max: int = Field(default=3, validation_alias="LOOP_MAX")
    coverage_threshold: float = Field(default=0.65, validation_alias="COVERAGE_THRESHOLD")
    chitchat_intent_heuristic: bool = Field(default=True, validation_alias="CHITCHAT_INTENT_HEURISTIC")
    # Cited answer: LLM retries when citation formatting fails (expensive). Default 0 = one LLM call + local repair only.
    citation_assert_retries: int = Field(default=0, validation_alias="CITATION_ASSERT_RETRIES")
    # Seconds to skip an LLM/embedding provider after a failure before trying it again.
    provider_failure_cooldown_seconds: float = Field(
        default=60.0,
        validation_alias="PROVIDER_FAILURE_COOLDOWN_SECONDS",
    )

    # Observability (logs-only correlation for now)
    langfuse_secret_key: str | None = Field(default=None, validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_public_key: str | None = Field(default=None, validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_host: str | None = Field(default=None, validation_alias="LANGFUSE_HOST")

    # Internal auth (service-to-service)
    internal_token: str | None = Field(default=None, validation_alias="INTERNAL_TOKEN")


@lru_cache
def get_settings() -> Settings:
    return Settings()

