"""Normalize DATABASE_URL for sync SQLAlchemy engines (psycopg3)."""


def sync_sqlalchemy_database_url(url: str) -> str:
    """Map SQLAlchemy async URLs to the sync driver used by the API and Alembic."""
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql+asyncpg://")
    return url
