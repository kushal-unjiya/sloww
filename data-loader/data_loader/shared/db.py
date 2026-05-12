from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection, connect
from psycopg.rows import dict_row

from data_loader.config import get_settings


def _psycopg_conninfo(url: str) -> str:
    """Strip SQLAlchemy driver prefixes; libpq/psycopg.connect expects postgresql://."""
    for prefix in (
        "postgresql+psycopg://",
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
    ):
        if url.startswith(prefix):
            return "postgresql://" + url.removeprefix(prefix)
    return url


@contextmanager
def get_connection() -> Iterator[Connection]:
    settings = get_settings()
    conn = connect(
        _psycopg_conninfo(settings.database_url),
        row_factory=dict_row,
        autocommit=False,
    )
    try:
        yield conn
    finally:
        conn.close()
