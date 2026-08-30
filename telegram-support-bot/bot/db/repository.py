"""Data-access layer. All SQLite/SQLAlchemy calls go through this repository."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from bot.db.engine import session_scope
from bot.db.models import BannedUser, Keyword, ResponsibleUser
from bot.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class SupportRepository:
    """CRUD helpers for keywords, responsible users, and bans."""

    def list_keywords(self) -> list[str]:
        try:
            with session_scope() as session:
                rows = session.scalars(select(Keyword.word).order_by(Keyword.word)).all()
                return list(rows)
        except SQLAlchemyError as exc:
            logger.exception("Failed to load keywords")
            raise DatabaseError("Could not load keywords") from exc

    def add_keyword(self, word: str) -> bool:
        """Insert a keyword. Returns True if it was newly added."""
        normalized = word.strip().lower()
        if not normalized:
            return False
        try:
            with session_scope() as session:
                existing = session.scalar(select(Keyword).where(Keyword.word == normalized))
                if existing:
                    return False
                session.add(Keyword(word=normalized))
                return True
        except SQLAlchemyError as exc:
            logger.exception("Failed to add keyword %r", normalized)
            raise DatabaseError("Could not add keyword") from exc

    def remove_keyword(self, word: str) -> bool:
        normalized = word.strip().lower()
        try:
            with session_scope() as session:
                row = session.scalar(select(Keyword).where(Keyword.word == normalized))
                if row is None:
                    return False
                session.delete(row)
                return True
        except SQLAlchemyError as exc:
            logger.exception("Failed to remove keyword %r", normalized)
            raise DatabaseError("Could not remove keyword") from exc

    def list_responsible(self) -> list[str]:
        try:
            with session_scope() as session:
                rows = session.scalars(
                    select(ResponsibleUser.username).order_by(ResponsibleUser.username)
                ).all()
                return list(rows)
        except SQLAlchemyError as exc:
            logger.exception("Failed to load responsible users")
            raise DatabaseError("Could not load responsible users") from exc

    def add_responsible(self, username: str) -> bool:
        normalized = username.lstrip("@").strip()
        if not normalized:
            return False
        try:
            with session_scope() as session:
                existing = session.scalar(
                    select(ResponsibleUser).where(ResponsibleUser.username == normalized)
                )
                if existing:
                    return False
                session.add(ResponsibleUser(username=normalized))
                return True
        except SQLAlchemyError as exc:
            logger.exception("Failed to add responsible user %r", normalized)
            raise DatabaseError("Could not add responsible user") from exc

    def remove_responsible(self, username: str) -> bool:
        normalized = username.lstrip("@").strip()
        try:
            with session_scope() as session:
                row = session.scalar(
                    select(ResponsibleUser).where(ResponsibleUser.username == normalized)
                )
                if row is None:
                    return False
                session.delete(row)
                return True
        except SQLAlchemyError as exc:
            logger.exception("Failed to remove responsible user %r", normalized)
            raise DatabaseError("Could not remove responsible user") from exc

    def is_banned(self, user_id: int) -> bool:
        try:
            with session_scope() as session:
                row = session.get(BannedUser, user_id)
                return row is not None
        except SQLAlchemyError as exc:
            logger.exception("Failed to check ban for user_id=%s", user_id)
            raise DatabaseError("Could not check ban status") from exc

    def ban_user(self, user_id: int, reason: str = "") -> None:
        try:
            with session_scope() as session:
                row = session.get(BannedUser, user_id)
                if row:
                    row.reason = reason
                    row.banned_at = datetime.now(timezone.utc)
                else:
                    session.add(
                        BannedUser(
                            user_id=user_id,
                            reason=reason,
                            banned_at=datetime.now(timezone.utc),
                        )
                    )
        except SQLAlchemyError as exc:
            logger.exception("Failed to ban user_id=%s", user_id)
            raise DatabaseError("Could not ban user") from exc

    def unban_user(self, user_id: int) -> bool:
        try:
            with session_scope() as session:
                row = session.get(BannedUser, user_id)
                if row is None:
                    return False
                session.delete(row)
                return True
        except SQLAlchemyError as exc:
            logger.exception("Failed to unban user_id=%s", user_id)
            raise DatabaseError("Could not unban user") from exc

    def list_banned(self) -> list[BannedUser]:
        try:
            with session_scope() as session:
                rows = session.scalars(
                    select(BannedUser).order_by(BannedUser.banned_at.desc())
                ).all()
                # Detach values we need after the session closes.
                return [
                    BannedUser(user_id=row.user_id, reason=row.reason, banned_at=row.banned_at)
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list banned users")
            raise DatabaseError("Could not list banned users") from exc

    def seed_if_empty(self, keywords: list[str], responsible: list[str]) -> None:
        """Insert default rows when tables are empty (idempotent)."""
        try:
            with session_scope() as session:
                if session.scalar(select(Keyword.id).limit(1)) is None:
                    session.add_all([Keyword(word=word.lower()) for word in keywords])
                    logger.info("Seeded %s default keywords", len(keywords))
                if session.scalar(select(ResponsibleUser.id).limit(1)) is None:
                    session.add_all(
                        [ResponsibleUser(username=name) for name in responsible]
                    )
                    logger.info("Seeded %s default responsible users", len(responsible))
        except SQLAlchemyError as exc:
            logger.exception("Failed to seed database")
            raise DatabaseError("Could not seed database") from exc
