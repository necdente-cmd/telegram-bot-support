"""Data-access layer. All SQLite/SQLAlchemy calls go through this repository."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from bot.db.engine import session_scope
from bot.db.models import BannedUser, Keyword, KnowledgeBase, ResponsibleUser
from bot.exceptions import DatabaseError

logger = logging.getLogger(__name__)


# ---------- Синонимы для поиска по смыслу без embeddings ----------
SYNONYMS: dict[str, set[str]] = {
    "зависает": {"катып", "жатат", "висит", "завис", "зависать", "тормозит", "фризит"},
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
    """Грубый стемминг для русских/кыргызских слов: убираем частые окончания."""
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
    """Извлекает значимые слова (>3 символов), стеммит их и добавляет синонимы."""
    words = re.findall(r"\w+", text.lower())
    result: set[str] = set()
    for w in words:
        if len(w) <= 3:
            continue
        stemmed = _stem(w)
        result.add(stemmed)
        # Добавляем синонимы (и их стемы)
        for syn in SYNONYMS.get(w, set()):
            if len(syn) > 3:
                result.add(_stem(syn))
    return result


class SupportRepository:
    """CRUD helpers for keywords, responsible users, bans, and knowledge base."""

    # ---------- Keywords ----------
    def list_keywords(self) -> list[str]:
        try:
            with session_scope() as session:
                rows = session.scalars(select(Keyword.word).order_by(Keyword.word)).all()
                return list(rows)
        except SQLAlchemyError as exc:
            logger.exception("Failed to load keywords")
            raise DatabaseError("Could not load keywords") from exc

    def add_keyword(self, word: str) -> bool:
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

    # ---------- Responsible users ----------
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

    # ---------- Bans ----------
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
                    session.add(BannedUser(
                        user_id=user_id, reason=reason,
                        banned_at=datetime.now(timezone.utc),
                    ))
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
                return [
                    BannedUser(user_id=r.user_id, reason=r.reason, banned_at=r.banned_at)
                    for r in rows
                ]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list banned users")
            raise DatabaseError("Could not list banned users") from exc

    # ---------- Knowledge Base (RAG) ----------
    def add_solution(self, problem_text: str, solution_text: str) -> None:
        keywords = " ".join(_extract_words(problem_text))
        try:
            with session_scope() as session:
                session.add(KnowledgeBase(
                    problem_text=problem_text,
                    solution_text=solution_text,
                    keywords=keywords,
                ))
        except SQLAlchemyError as exc:
            logger.exception("Failed to add knowledge base entry")
            raise DatabaseError("Could not add solution") from exc

    def search_solutions(self, query_text: str, min_matches: int = 1, limit: int = 3) -> list[str]:
        """Взвешенный поиск: редкие совпадения весят больше, чем частые."""
        query_words = _extract_words(query_text)
        if not query_words:
            return []
        try:
            with session_scope() as session:
                rows = session.scalars(select(KnowledgeBase)).all()
                if not rows:
                    return []

                # Считаем частоту слов во всей базе (IDF)
                all_kb_words: dict[str, int] = {}
                parsed: list[tuple[object, set[str]]] = []
                for row in rows:
                    kb_words = set((row.keywords or "").split())
                    parsed.append((row, kb_words))
                    for w in kb_words:
                        all_kb_words[w] = all_kb_words.get(w, 0) + 1

                # Взвешенный счёт для каждой записи
                scored: list[tuple[float, str]] = []
                total_docs = len(parsed)
                for row, kb_words in parsed:
                    common = query_words & kb_words
                    if not common:
                        continue
                    score = 0.0
                    for w in common:
                        # IDF: редкое слово = высокий вес
                        idf = 1.0 + (1.0 / max(all_kb_words.get(w, 1), 1))
                        score += idf
                    # Бонус за количество совпадений
                    score += 0.5 * (len(common) - 1)
                    scored.append((score, row.solution_text))

                scored.sort(reverse=True, key=lambda x: x[0])
                # Возвращаем только те, у кого score > порога
                return [sol for sc, sol in scored[:limit] if sc > 1.0]
        except SQLAlchemyError as exc:
            logger.exception("Failed to search solutions")
            raise DatabaseError("Could not search solutions") from exc

    def list_all_kb(self, limit: int = 20) -> list[KnowledgeBase]:
        try:
            with session_scope() as session:
                rows = session.scalars(
                    select(KnowledgeBase)
                    .order_by(KnowledgeBase.created_at.desc())
                    .limit(limit)
                ).all()
                return [
                    KnowledgeBase(
                        id=r.id, problem_text=r.problem_text,
                        solution_text=r.solution_text, keywords=r.keywords,
                        created_at=r.created_at,
                    ) for r in rows
                ]
        except SQLAlchemyError as exc:
            logger.exception("Failed to list knowledge base")
            raise DatabaseError("Could not list knowledge base") from exc

    def count_kb(self) -> int:
        try:
            with session_scope() as session:
                return session.query(KnowledgeBase).count()
        except SQLAlchemyError as exc:
            logger.exception("Failed to count knowledge base")
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
            logger.exception("Failed to delete knowledge base entry %s", kb_id)
            raise DatabaseError("Could not delete solution") from exc

    # ---------- Seed ----------
    def seed_if_empty(self, keywords: list[str], responsible: list[str]) -> None:
        try:
            with session_scope() as session:
                if session.scalar(select(Keyword.id).limit(1)) is None:
                    session.add_all([Keyword(word=w.lower()) for w in keywords])
                    logger.info("Seeded %s default keywords", len(keywords))
                if session.scalar(select(ResponsibleUser.id).limit(1)) is None:
                    session.add_all([ResponsibleUser(username=n) for n in responsible])
                    logger.info("Seeded %s default responsible users", len(responsible))
        except SQLAlchemyError as exc:
            logger.exception("Failed to seed database")
            raise DatabaseError("Could not seed database") from exc
