from collections.abc import Generator

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from api.config import get_settings
from api.shared.logging import get_logger, timer

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
logger = get_logger("sloww.db")


def init_db() -> None:
    global _engine, _SessionLocal
    settings = get_settings()
    t = timer()
    _engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={settings.db_schema},public"},
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    logger.info("db_initialized schema=%s elapsed_ms=%s", settings.db_schema, t.ms())


def dispose_db() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_engine() -> Engine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


def get_session() -> Generator[Session, None, None]:
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def new_session() -> Session:
    """Standalone session for work that outlives the request (e.g. after streaming ends). Caller must close()."""
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()


def check_database() -> bool:
    try:
        t = timer()
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.debug("db_ready elapsed_ms=%s", t.ms())
        return True
    except SQLAlchemyError:
        logger.exception("db_not_ready")
        return False
