"""Engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from bot.config import Settings
from bot.db.models import Base
from bot.exceptions import DatabaseError

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _sqlite_connect_pragmas(dbapi_connection, _connection_record) -> None:
    """Enable WAL and foreign keys for SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def init_engine(settings: Settings) -> Engine:
    """Create (or return) the global SQLAlchemy engine."""
    global _engine, _SessionLocal
    if _engine is not None:
        return _engine

    url = settings.sqlalchemy_url
    connect_args = {}
    if url.startswith("sqlite"):
        # Required for SQLite + threads used by the Telegram polling loop.
        connect_args["check_same_thread"] = False

    _engine = create_engine(
        url,
        echo=False,
        future=True,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    if url.startswith("sqlite"):
        event.listen(_engine, "connect", _sqlite_connect_pragmas)

    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise DatabaseError("Database engine is not initialized. Call init_engine() first.")
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope. Rolls back on errors."""
    if _SessionLocal is None:
        raise DatabaseError("Database engine is not initialized. Call init_engine() first.")
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all_tables() -> None:
    """Fallback schema create used only if Alembic is unavailable."""
    Base.metadata.create_all(bind=get_engine())
