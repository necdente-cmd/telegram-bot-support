"""SQLAlchemy models for the support bot."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base used by Alembic and the runtime engine."""


class Keyword(Base):
    """Phrase that triggers a troubleshooting-advice reply."""

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


class ResponsibleUser(Base):
    """Telegram username (without @) that should be mentioned on escalation."""

    __tablename__ = "responsible_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class BannedUser(Base):
    """User blocked from interacting with the bot."""

    __tablename__ = "banned_users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    banned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
