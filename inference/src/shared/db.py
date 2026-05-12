from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings
from src.shared.logging import get_logger, timer

logger = get_logger("sloww.inference.db")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return
    settings = get_settings()
    t = timer()
    url = settings.database_url
    schema = settings.db_schema
    connect_args: dict = {}

    # Dialect-specific search_path injection:
    # - asyncpg supports `server_settings`
    # - psycopg uses `options` flag
    if "asyncpg" in url:
        connect_args = {"server_settings": {"search_path": f"{schema},public"}}
    else:
        connect_args = {"options": f"-csearch_path={schema},public"}

    _engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
        connect_args=connect_args,
    )
    _sessionmaker = async_sessionmaker(bind=_engine, expire_on_commit=False)
    logger.info(
        "db_initialized",
        extra={"event": "db_initialized", "latency_ms": t.ms()},
    )


async def dispose_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def get_engine() -> AsyncEngine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _sessionmaker is None:
        init_db()
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        yield session


async def check_database() -> bool:
    try:
        t = timer()
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.debug("db_ready", extra={"event": "db_ready", "latency_ms": t.ms()})
        return True
    except SQLAlchemyError:
        logger.exception("db_not_ready", extra={"event": "db_not_ready"})
        return False


def qualify_table(*, schema: str, table: str) -> str:
    schema2 = (schema or "").strip()
    if not schema2:
        return table
    return f"{schema2}.{table}"

