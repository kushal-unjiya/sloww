import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool, text

from api.shared.db_url import sync_sqlalchemy_database_url

# `.env` is not loaded into the shell automatically; Alembic only sees `os.environ`.
# Try `backend/.env` then monorepo root `.env` (common when running from `backend/`).
_migrations_dir = Path(__file__).resolve().parent
_app_dir = _migrations_dir.parent
_repo_root = _app_dir.parent
for _env_path in (_app_dir / ".env", _repo_root / ".env"):
    if _env_path.is_file():
        load_dotenv(_env_path)
        break

config = context.config

if config.config_file_name is not None:
    # Alembic will load logging configuration from alembic.ini
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL env var not set")

database_url = sync_sqlalchemy_database_url(database_url)

# Alembic version table lives here; must match migrations (`schema="sloww_ai"` on tables).
db_schema = os.environ.get("DB_SCHEMA", "sloww_ai")

# We hand-author migrations; there are no SQLAlchemy model metadata imports yet.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table="alembic_version",
        version_table_schema=db_schema,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url, poolclass=pool.NullPool)

    with engine.connect() as connection:
        # If the version table lives outside `public`, that schema must exist
        # before Alembic creates `alembic_version`. Migration 001 also creates
        # `sloww_ai`, but it never runs if this step fails first.
        if db_schema and db_schema != "public":
            connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {db_schema}"))
            connection.commit()

        # App tables live in `sloww_ai`. Extensions (pgcrypto) install into `public`.
        # Some DBs are created without `public`; create it so search_path + CREATE EXTENSION work.
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS sloww_ai"))
        connection.execute(text("SET search_path TO public, sloww_ai"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table="alembic_version",
            version_table_schema=db_schema,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

