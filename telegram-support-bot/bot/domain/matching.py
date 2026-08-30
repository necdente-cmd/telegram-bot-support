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


class MessageMatcher:
    """Classify incoming user text against configured phrase lists."""

    def __init__(self, keywords: list[str] | None = None) -> None:
        self._keywords: list[str] = list(keywords or [])
        self._about_bot_regex = [re.compile(pattern, re.IGNORECASE) for pattern in ABOUT_BOT_PATTERNS]

    def replace_keywords(self, keywords: list[str]) -> None:
        """Refresh the in-memory keyword cache after DB updates or reload."""
        self._keywords = list(keywords)

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
        lowered = text.lower()
        return any(keyword in lowered for keyword in self._keywords)


class AdviceService:
    """Pick a troubleshooting tip for keyword matches."""

    def __init__(self, advice_items: list[str] | None = None) -> None:
        self._items = list(advice_items or ADVICE_LIST)

    def random_advice(self) -> str:
        return random.choice(self._items)
