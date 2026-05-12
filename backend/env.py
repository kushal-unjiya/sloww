import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from api.shared.db_url import sync_sqlalchemy_database_url


config = context.config

if config.config_file_name is not None:
    # Alembic will load logging configuration from alembic.ini
    fileConfig(config.config_file_name)

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL env var not set")

database_url = sync_sqlalchemy_database_url(database_url)

db_schema = os.environ.get("DB_SCHEMA", "public")

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

