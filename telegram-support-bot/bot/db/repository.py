"""Data-access layer. All SQLite/SQLAlchemy calls go through this repository."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db.engine import session_scope
from bot.db.models import (
    BannedUser,
    Feedback,
    KbVote,
    Keyword,
    KnowledgeBase,
    MessageLog,
    ResponsibleUser,
)
from bot.exceptions import DatabaseError

logger = logging.getLogger(__name__)


SYNONYMS: dict[str, set[str]] = {
    "зависает": {"катып", "жатат", "висит", "завис", "зависать", "тормозит", "фризит", "глючит", "лагает", "лаги"},
    "катып": {"зависает", "жатат", "висит", "завис", "фризит"},
    "жатат": {"зависает", "катып"},
    "тормозит": {"зависает", "медленно", "жай", "иштейт", "лаг"},
    "медленно": {"тормозит", "жай", "иштейт"},
    "жай": {"медленно", "тормозит", "иштейт"},
    "работает": {"иштейт", "иштеп"},
    "иштейт": {"работает", "иштеп"},
    "не": {"жок", "иштебей"},
    "жок": {"не", "иштебей"},
    "ошибка": {"баг", "глюк", "error", "проблема", "ката"},
    "баг": {"ошибка", "глюк", "проблема"},
    "глюк": {"ошибка", "баг", "проблема"},
    "открывается": {"ачылат", "грузит", "загружается"},
    "ачылат": {"открывается", "грузит"},
    "грузит": {"открывается", "загружается"},
    "сайт": {"мис", "система", "портал"},
    "мис": {"сайт", "система"},
    "система": {"сайт", "мис", "программа"},
    "пароль": {"password", "логин", "login", "вход"},
    "вход": {"пароль", "логин", "login"},
    "печать": {"принтер", "распечатать", "печатает"},
    "принтер": {"печать", "распечатать"},
    "медкарта": {"карта", "пациент", "амбулаторная", "стационарная"},
    "карта": {"медкарта", "пациент"},
    "пациент": {"карта", "медкарта"},
    "больничный": {"лвн", "лист", "нетрудоспособности"},
    "лвн": {"больничный", "лист"},
}


def _stem(word: str) -> str:
    if len(word) <= 4:
        return word
    for suffix in (
        "ается", "яется", "ится", "ется", "ает", "яет", "ует",
        "ат", "ят", "ет", "ит", "ут", "ют", "ать", "ять", "ить", "еть",
        "ами", "ями", "ов", "ев", "ах", "ях", "ой", "ей", "ый", "ий",
        "ая", "яя", "ое", "ее", "ые", "ие", "ам", "ям", "ом", "ем",
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _extract_words(text: str) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    result: set[str] = set()
    for w in words:
        if len(w) <= 3:
            continue
        stemmed = _stem(w)
        result.add(stemmed)
        for syn in SYNONYMS.get(w, set()):
            if len(syn) > 3:
                result.add(_stem(syn))
    return result


def _signature(text: str) -> str:
    """Нормализованный ключ проблемы для группировки в /top."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return normalized[:150]


class SupportRepository:

    # ---------- Keywords ----------
    def list_keywords(self) -> list[str]:
        try:
            with session_scope() as session:
                return list(session.scalars(select(Keyword.word).order_by(Keyword.word)).all())
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not load keywords") from exc

    def add_keyword(self, word: str) -> bool:
        normalized = word.strip().lower()
        if not normalized:
            return False
        try:
            with session_scope() as session:
                if session.scalar(select(Keyword).where(Keyword.word == normalized)):
                    return False
                session.add(Keyword(word=normalized))
                return True
        except SQLAlchemyError as exc:
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
            raise DatabaseError("Could not remove keyword") from exc

    # ---------- Responsible users ----------
    def list_responsible(self) -> list[str]:
        try:
            with session_scope() as session:
                return list(session.scalars(
                    select(ResponsibleUser.username).order_by(ResponsibleUser.username)
                ).all())
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not load responsible users") from exc

    def add_responsible(self, username: str) -> bool:
        normalized = username.lstrip("@").strip()
        if not normalized:
            return False
        try:
            with session_scope() as session:
                if session.scalar(select(ResponsibleUser).where(ResponsibleUser.username == normalized)):
                    return False
                session.add(ResponsibleUser(username=normalized))
                return True
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not add responsible user") from exc

    def remove_responsible(self, username: str) -> bool:
        normalized = username.lstrip("@").strip()
        try:
            with session_scope() as session:
                row = session.scalar(select(ResponsibleUser).where(ResponsibleUser.username == normalized))
                if row is None:
                    return False
                session.delete(row)
                return True
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not remove responsible user") from exc

    # ---------- Bans ----------
    def is_banned(self, user_id: int) -> bool:
        try:
            with session_scope() as session:
                return session.get(BannedUser, user_id) is not None
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not check ban status") from exc

    def ban_user(self, user_id: int, reason: str = "") -> None:
        try:
            with session_scope() as session:
                row = session.get(BannedUser, user_id)
                if row:
                    row.reason = reason
                    row.banned_at = datetime.now(timezone.utc)
                else:
                    session.add(BannedUser(user_id=user_id, reason=reason, banned_at=datetime.now(timezone.utc)))
        except SQLAlchemyError as exc:
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
            raise DatabaseError("Could not unban user") from exc

    def list_banned(self) -> list[BannedUser]:
        try:
            with session_scope() as session:
                rows = session.scalars(select(BannedUser).order_by(BannedUser.banned_at.desc())).all()
                return [BannedUser(user_id=r.user_id, reason=r.reason, banned_at=r.banned_at) for r in rows]
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not list banned users") from exc

    # ---------- Knowledge Base (RAG) ----------
    def add_solution(self, problem_text: str, solution_text: str) -> int:
        keywords = " ".join(_extract_words(problem_text))
        try:
            with session_scope() as session:
                kb = KnowledgeBase(
                    problem_text=problem_text,
                    solution_text=solution_text,
                    keywords=keywords,
                    rating=0,
                )
                session.add(kb)
                session.flush()
                return kb.id
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not add solution") from exc

    def search_solutions(self, query_text: str, min_matches: int = 1, limit: int = 3) -> list[tuple[int, str]]:
        query_words = _extract_words(query_text)
        if not query_words:
            return []
        try:
            with session_scope() as session:
                rows = session.scalars(select(KnowledgeBase)).all()
                if not rows:
                    return []
                all_kb_words: dict[str, int] = {}
                parsed = []
                for row in rows:
                    kb_words = set((row.keywords or "").split())
                    parsed.append((row, kb_words))
                    for w in kb_words:
                        all_kb_words[w] = all_kb_words.get(w, 0) + 1
                scored = []
                for row, kb_words in parsed:
                    common = query_words & kb_words
                    if not common:
                        continue
                    score = 0.0
                    for w in common:
                        idf = 1.0 + (1.0 / max(all_kb_words.get(w, 1), 1))
                        score += idf
                    score += 0.5 * (len(common) - 1)
                    scored.append((score, row.id, row.solution_text))
                scored.sort(reverse=True, key=lambda x: x[0])
                return [(kb_id, sol) for sc, kb_id, sol in scored[:limit] if sc > 1.0]
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not search solutions") from exc

    def rate_kb(self, kb_id: int, delta: int) -> int:
        try:
            with session_scope() as session:
                row = session.get(KnowledgeBase, kb_id)
                if row is None:
                    return 0
                row.rating = (row.rating or 0) + delta
                new_rating = row.rating
                if new_rating <= -3:
                    session.delete(row)
                    logger.info("KB #%s удалён (рейтинг %s)", kb_id, new_rating)
                    return -999
                return new_rating
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not rate kb") from exc

    def list_all_kb(self, limit: int = 20) -> list[KnowledgeBase]:
        try:
            with session_scope() as session:
                rows = session.scalars(
                    select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).limit(limit)
                ).all()
                return [
                    KnowledgeBase(
                        id=r.id, problem_text=r.problem_text, solution_text=r.solution_text,
                        keywords=r.keywords, rating=r.rating, created_at=r.created_at,
                    ) for r in rows
                ]
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not list knowledge base") from exc

    def count_kb(self) -> int:
        try:
            with session_scope() as session:
                return session.query(KnowledgeBase).count()
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not count knowledge base") from exc

    def delete_kb(self, kb_id: int) -> bool:
        try:
            with session_scope() as session:
                row = session.get(KnowledgeBase, kb_id)
                if row is None:
                    return False
                session.delete(row)
                return True
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not delete solution") from exc

    def get_kb_stats(self) -> dict:
        try:
            with session_scope() as session:
                rows = session.scalars(select(KnowledgeBase)).all()
                total = len(rows)
                if total == 0:
                    return {"total": 0, "avg_rating": 0.0, "top": [], "negative": [], "deleted_ready": 0}
                ratings = [r.rating or 0 for r in rows]
                avg = sum(ratings) / total
                top = sorted(rows, key=lambda r: (r.rating or 0), reverse=True)[:5]
                top_data = [{"id": r.id, "problem": r.problem_text[:60], "rating": r.rating or 0} for r in top]
                negative = [
                    {"id": r.id, "problem": r.problem_text[:60], "rating": r.rating or 0}
                    for r in rows if (r.rating or 0) < 0
                ]
                ready = sum(1 for r in rows if (r.rating or 0) <= -2)
                return {
                    "total": total, "avg_rating": round(avg, 2),
                    "top": top_data, "negative": negative, "deleted_ready": ready,
                }
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not get KB stats") from exc

    # ---------- KbVote (защита от повторного голоса) ----------
    def has_voted_kb(self, kb_id: int, user_id: int) -> bool:
        try:
            with session_scope() as session:
                existing = session.scalar(
                    select(KbVote).where(KbVote.kb_id == kb_id, KbVote.user_id == user_id)
                )
                return existing is not None
        except SQLAlchemyError:
            return False

    def register_kb_vote(self, kb_id: int, user_id: int, vote: int) -> None:
        try:
            with session_scope() as session:
                session.add(KbVote(kb_id=kb_id, user_id=user_id, vote=vote))
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not register vote") from exc

    # ---------- Логирование сообщений ----------
    def log_message(
        self,
        user_id: int,
        username: str | None,
        chat_id: int,
        text: str,
        matched_kb_id: int | None = None,
        answered_by_rag: int = 0,
    ) -> None:
        try:
            with session_scope() as session:
                session.add(MessageLog(
                    user_id=user_id,
                    username=(username or "")[:64],
                    chat_id=chat_id,
                    text=text[:2000],
                    signature=_signature(text),
                    matched_kb_id=matched_kb_id,
                    answered_by_rag=answered_by_rag,
                ))
        except SQLAlchemyError:
            logger.exception("Failed to log message")

    def get_top_problems(self, days: int = 7, limit: int = 5) -> list[tuple[str, int]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        try:
            with session_scope() as session:
                rows = session.execute(
                    select(MessageLog.signature, func.count(MessageLog.id))
                    .where(MessageLog.created_at >= cutoff)
                    .group_by(MessageLog.signature)
                    .order_by(func.count(MessageLog.id).desc())
                    .limit(limit)
                ).all()
                return [(row[0], row[1]) for row in rows]
        except SQLAlchemyError:
            logger.exception("Failed to get top problems")
            return []

    def get_daily_stats(self, hours: int = 24) -> dict:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        try:
            with session_scope() as session:
                total = session.scalar(
                    select(func.count(MessageLog.id)).where(MessageLog.created_at >= cutoff)
                ) or 0
                rag_count = session.scalar(
                    select(func.count(MessageLog.id)).where(
                        MessageLog.created_at >= cutoff,
                        MessageLog.answered_by_rag == 1,
                    )
                ) or 0
                new_kb = session.scalar(
                    select(func.count(KnowledgeBase.id)).where(KnowledgeBase.created_at >= cutoff)
                ) or 0
                feedback_count = session.scalar(
                    select(func.count(Feedback.id)).where(Feedback.created_at >= cutoff)
                ) or 0
                return {
                    "total": total, "rag": rag_count,
                    "escalated": total - rag_count,
                    "new_kb": new_kb, "feedback": feedback_count,
                }
        except SQLAlchemyError:
            logger.exception("Failed to get daily stats")
            return {"total": 0, "rag": 0, "escalated": 0, "new_kb": 0, "feedback": 0}

    # ---------- Feedback ----------
    def add_feedback(self, user_id: int, username: str | None, text: str) -> int:
        try:
            with session_scope() as session:
                fb = Feedback(user_id=user_id, username=(username or "")[:64], text=text[:2000])
                session.add(fb)
                session.flush()
                return fb.id
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not add feedback") from exc

    def list_feedback(self, limit: int = 20) -> list[Feedback]:
        try:
            with session_scope() as session:
                rows = session.scalars(
                    select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
                ).all()
                return [
                    Feedback(
                        id=r.id, user_id=r.user_id, username=r.username,
                        text=r.text, created_at=r.created_at,
                    ) for r in rows
                ]
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not list feedback") from exc

    # ---------- Seed ----------
    def seed_if_empty(self, keywords: list[str], responsible: list[str]) -> None:
        try:
            with session_scope() as session:
                if session.scalar(select(Keyword.id).limit(1)) is None:
                    session.add_all([Keyword(word=w.lower()) for w in keywords])
                if session.scalar(select(ResponsibleUser.id).limit(1)) is None:
                    session.add_all([ResponsibleUser(username=n) for n in responsible])
        except SQLAlchemyError as exc:
            raise DatabaseError("Could not seed database") from exc
