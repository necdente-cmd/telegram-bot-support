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

# Слова-маркеры, что это «проблема с системой» (а не болтовня)
_PROBLEM_MARKERS = [
    "не работает", "не открывается", "не грузит", "не сохраняется",
    "зависает", "завис", "тормозит", "медленно",
    "ошибка", "баг", "глюк", "сбой", "проблема", "ката",
    "иштебей", "катып", "иштебейт", "жай иштейт", "тутап",
    "катып жатат", "катып калды", "иштебей жатат", "иштебей калды",
    "не печатает", "не выгружается", "не приходит",
    "не могу зайти", "не заходит", "не пускает",
    "почему не", "что с", "а что с",
]

# Слова-маркеры запроса на доработку
_FEATURE_MARKERS = [
    "просим", "предлагаем", "необходимо", "нужно добавить",
    "добавьте", "хотелось бы", "было бы хорошо",
    "требуется", "улучшить", "изменить", "доработать",
]

_STOP_WORDS = {
    "и", "в", "не", "на", "с", "по", "для", "что", "как", "это",
    "или", "но", "а", "у", "к", "о", "об", "из", "за",
    "жатат", "болуп", "менен", "үчүн",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    return {w for w in words if len(w) >= 4 and w not in _STOP_WORDS}


class MessageMatcher:
    """Classify incoming user text against configured phrase lists."""

    def __init__(self, keywords: list[str] | None = None) -> None:
        self._keywords: list[str] = list(keywords or [])
        self._about_bot_regex = [re.compile(p, re.IGNORECASE) for p in ABOUT_BOT_PATTERNS]
        self._keyword_tokens: set[str] = set()
        for kw in self._keywords:
            self._keyword_tokens |= _tokenize(kw)

    def replace_keywords(self, keywords: list[str]) -> None:
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
        """Совпадение по фразе или по отдельным словам."""
        lowered = text.lower()
        for keyword in self._keywords:
            if keyword in lowered:
                return True
        text_tokens = _tokenize(text)
        if not text_tokens:
            return False
        return bool(text_tokens & self._keyword_tokens)

    def is_support_problem(self, text: str) -> bool:
        """Проверяет, является ли сообщение описанием ПРОБЛЕМЫ (а не болтовнёй).

        Примеры проблем: «база зависает», «ошибка при входе», «не открывается карта»
        Примеры НЕ проблем: «2+2», «какой сегодня день», «привет»
        """
        lowered = text.lower()
        return any(marker in lowered for marker in _PROBLEM_MARKERS)

    def is_feature_request(self, text: str) -> bool:
        """Проверяет, является ли сообщение запросом на доработку."""
        lowered = text.lower()
        return any(marker in lowered for marker in _FEATURE_MARKERS)


class AdviceService:
    """Pick a troubleshooting tip for keyword matches."""

    def __init__(self, advice_items: list[str] | None = None) -> None:
        self._items = list(advice_items or ADVICE_LIST)

    def random_advice(self) -> str:
        return random.choice(self._items)
