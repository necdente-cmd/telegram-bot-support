"""Text matching and advice selection (pure business logic, no I/O)."""

from __future__ import annotations

import random
import re

from bot.data.phrases import (
    ABOUT_BOT_PATTERNS,
    ADVICE_LIST,
    HELP_PHRASES,
    TECHNICAL_WORKS_PHRASES,
)

# Стоп-слова: слишком частые, их игнорируем при поиске по словам
_STOP_WORDS = {
    "и", "в", "не", "на", "с", "по", "для", "что", "как", "это",
    "или", "но", "а", "у", "к", "о", "об", "из", "за",
    "жатат", "болуп", "менен", "үчүн",  # кыргызские частые
}


def _tokenize(text: str) -> set[str]:
    """Разбивает текст на значимые слова (длина >= 4)."""
    words = re.findall(r"\w+", text.lower())
    return {w for w in words if len(w) >= 4 and w not in _STOP_WORDS}


class MessageMatcher:
    """Classify incoming user text against configured phrase lists."""

    def __init__(self, keywords: list[str] | None = None) -> None:
        self._keywords: list[str] = list(keywords or [])
        self._about_bot_regex = [re.compile(p, re.IGNORECASE) for p in ABOUT_BOT_PATTERNS]
        # Заранее нарезаем ключевые слова на токены для быстрого поиска
        self._keyword_tokens: set[str] = set()
        for kw in self._keywords:
            self._keyword_tokens |= _tokenize(kw)

    def replace_keywords(self, keywords: list[str]) -> None:
        """Refresh the in-memory keyword cache after DB updates or reload."""
        self._keywords = list(keywords)
        self._keyword_tokens = set()
        for kw in self._keywords:
            self._keyword_tokens |= _tokenize(kw)

    @property
    def keywords(self) -> list[str]:
        return list(self._keywords)

    def mentions_bot(self, text: str, bot_username: str) -> bool:
        return f"@{bot_username}".lower() in text.lower()

    def is_about_bot(self, text: str) -> bool:
        lowered = text.lower()
        return any(pattern.search(lowered) for pattern in self._about_bot_regex)

    def is_technical_works(self, text: str) -> bool:
        lowered = text.lower()
        return any(phrase in lowered for phrase in TECHNICAL_WORKS_PHRASES)

    def is_help_request(self, text: str) -> bool:
        lowered = text.lower()
        return any(phrase in lowered for phrase in HELP_PHRASES)

    def matches_keyword(self, text: str) -> bool:
        """Ищет совпадения:
        1) по полной фразе (точное вхождение)
        2) по отдельным словам — минимум 1 совпадение
        """
        lowered = text.lower()

        # Точное вхождение фразы
        for keyword in self._keywords:
            if keyword in lowered:
                return True

        # По токенам (словам длиной >= 4)
        text_tokens = _tokenize(text)
        if not text_tokens:
            return False

        # Совпадение хотя бы одного значимого слова
        return bool(text_tokens & self._keyword_tokens)


class AdviceService:
    """Pick a troubleshooting tip for keyword matches."""

    def __init__(self, advice_items: list[str] | None = None) -> None:
        self._items = list(advice_items or ADVICE_LIST)

    def random_advice(self) -> str:
        return random.choice(self._items)
