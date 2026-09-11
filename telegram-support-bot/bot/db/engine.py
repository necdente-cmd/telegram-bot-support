"""Engine and session factory."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from bot.config import Settings
from bot.db.models import Base
from bot.exceptions import DatabaseError

logger = logging.getLogger(__name__)

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


def ensure_columns() -> None:
    """Добавляет недостающие колонки/таблицы (idempotent).

    SQLAlchemy `create_all` не умеет ALTER TABLE для уже созданных таблиц,
    поэтому для SQLite делаем это вручную.
    """
    engine = get_engine()
    try:
        with engine.begin() as conn:
            # knowledge_base: rating
            result = conn.execute(text("PRAGMA table_info(knowledge_base)"))
            existing = {row[1] for row in result.fetchall()}
            if existing and "rating" not in existing:
                conn.execute(
                    text("ALTER TABLE knowledge_base ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
                )
                logger.info("Добавлена колонка 'rating' в knowledge_base")

            # kb_votes — на всякий случай (если create_all пропустит)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS kb_votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kb_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    vote INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(kb_id, user_id)
                )
            """))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kb_votes_kb_id ON kb_votes(kb_id)"))
    except Exception as exc:
        logger.error("ensure_columns failed (continuing): %s", exc)
