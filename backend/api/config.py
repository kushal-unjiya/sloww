import re
from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.shared.db_url import sync_sqlalchemy_database_url

_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Service-local only; Docker Compose uses compose.env separately.
        env_file=(".env",),
        extra="ignore",
    )

    database_url: str  # DATABASE_URL
    db_schema: str = "sloww_ai"

    clerk_jwks_url: str  # CLERK_JWKS_URL
    clerk_jwt_issuer: str  # CLERK_JWT_ISSUER
    clerk_secret_key: str | None = None  # CLERK_SECRET_KEY
    clerk_verify_audience: bool = False
    clerk_jwt_audience: str | None = None

    # Google Cloud Storage (required). Auth: Application Default Credentials — see .env.example.
    gcs_bucket_name: str = Field(validation_alias=AliasChoices("GCS_BUCKET_NAME"))
    gcs_project_id: str | None = Field(default=None, validation_alias=AliasChoices("GCS_PROJECT_ID"))

    # Optional dependency probes at startup (best-effort; logs only).
    inference_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BACKEND_INFERENCE_URL", "INFERENCE_URL"),
    )
    ui_url: str | None = Field(default=None, validation_alias="BACKEND_UI_URL")
    data_loader_url: str | None = Field(default=None, validation_alias="BACKEND_DATA_LOADER_URL")
    startup_probe_timeout_seconds: float = 1.5

    internal_token: str | None = None  # INTERNAL_TOKEN

    cors_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:3000,http://localhost:3000"
    )

    presign_expires_seconds: int = 3600
    max_upload_bytes: int = 50 * 1024 * 1024
    max_processing_per_user: int = 5

    # Pub/Sub (optional). When enabled, backend publishes after document registration commit.
    pubsub_enabled: bool = Field(default=False, validation_alias=AliasChoices("PUBSUB_ENABLED"))
    pubsub_project_id: str | None = Field(default=None, validation_alias=AliasChoices("PUBSUB_PROJECT_ID"))
    pubsub_ingestion_topic: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PUBSUB_INGESTION_TOPIC"),
    )

    @property
    def pubsub_ingestion_topic_full(self) -> str | None:
        """Fully-qualified topic path ``projects/{id}/topics/{name}``."""
        if not self.pubsub_project_id or not self.pubsub_ingestion_topic:
            return None
        tid = self.pubsub_ingestion_topic.strip()
        if tid.startswith("projects/"):
            return tid
        return f"projects/{self.pubsub_project_id}/topics/{tid}"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: object) -> object:
        if isinstance(v, str):
            return sync_sqlalchemy_database_url(v)
        return v

    @field_validator("db_schema")
    @classmethod
    def schema_safe(cls, v: str) -> str:
        if not _SCHEMA_RE.match(v):
            raise ValueError("invalid db_schema")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def reject_clerk_placeholders(self) -> "Settings":
        for name, url in (
            ("CLERK_JWKS_URL", self.clerk_jwks_url),
            ("CLERK_JWT_ISSUER", self.clerk_jwt_issuer),
        ):
            if "YOUR_INSTANCE" in url or "your_instance" in url.lower():
                raise ValueError(
                    f"{name} still contains the .env.example placeholder. "
                    "In Clerk Dashboard → your application → API Keys (or JWT), "
                    "copy the real JWKS URL and issuer for your instance "
                    "(e.g. https://happy-foo-12.clerk.accounts.dev)."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
