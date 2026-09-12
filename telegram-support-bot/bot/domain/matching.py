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

_PROBLEM_MARKERS = [
    "не работает", "не открывается", "не грузит", "не сохраняется",
    "зависает", "завис", "тормозит", "медленно",
    "ошибка", "баг", "глюк", "сбой", "проблема", "ката",
    "иштебей", "катып", "иштебейт", "жай иштейт", "тутап",
    "катып жатат", "катып калды", "иштебей жатат", "иштебей калды",
    "не могу", "не можем", "не получается", "не выходит",
    "не печатает", "не выгружается", "не приходит",
    "не могу зайти", "не заходит", "не пускает", "не скачать",
    "не скачивается", "не можем скачать", "не загружается",
    "плохо работает", "плохо иштейт", "плохо функционирует",
    "очень медленно", "ужасно работает", "плохо грузит",
    "норм будет", "нормально работать", "когда нибудь работать",
    "когда это закончится", "когда заработает",
    "надоело", "замучился", "одни возмущения", "одно возмущение",
    "невозможно работать", "достало",
    "опять не работает", "снова не работает",
    "уже неделю", "уже месяц", "давно не работает",
    "почему не", "что с", "а что с", "где ответ",
]

_FEATURE_MARKERS = [
    "просим", "предлагаем", "необходимо", "нужно добавить",
    "добавьте", "хотелось бы", "было бы хорошо",
    "требуется", "улучшить", "изменить", "доработать",
]

# Рабочие маркеры — темы, связанные с системой/медициной/документами.
# Если сообщение содержит хотя бы один из них, бот отвечает на него в группе.
_WORK_MARKERS = [
    # Медицина и документы
    "мсэк", "мсэ", "эхокг", "узи", "доплер", "лвн", "больничный",
    "нетрудоспособност", "пациент", "карта", "амбулаторн", "стационарн",
    "диагноз", "анализ", "исследован", "заключени", "прием", "приём",
    "талон", "запис", "врач", "категор", "классификат", "справочник",
    # МИС / Санарип
    "санарип", "санприп", "sanarip", "мис", "тундук", "түндүк",
    "цсм", "гсв", "оз", "фап", "пмсп", "ilab",
    # Документы системы
    "выписк", "отчет", "отчёт", "форм", "печать", "экспорт", "выгрузк",
    "справк", "направлени", "результат", "данн", "интеграци", "модул",
    "дашборд", "панел", "фильтр", "список", "карточк",
    # Технические
    "база", "система", "программ", "сайт", "сервер", "модуль",
    "ошибк", "сбой", "зависа", "тормоз", "не работает", "не открыва",
    "не грузит", "не сохран", "не скач", "не печат", "не выгруж",
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
        """Похоже ли сообщение на описание ПРОБЛЕМЫ."""
        lowered = text.lower()
        return any(marker in lowered for marker in _PROBLEM_MARKERS)

    def is_feature_request(self, text: str) -> bool:
        """Похоже ли сообщение на запрос доработки системы."""
        lowered = text.lower()
        return any(marker in lowered for marker in _FEATURE_MARKERS)

    def is_work_question(self, text: str) -> bool:
        """Похоже ли сообщение на рабочий вопрос (а не болтовню)."""
        lowered = text.lower()
        return any(marker in lowered for marker in _WORK_MARKERS)


class AdviceService:
    """Pick a troubleshooting tip for keyword matches."""

    def __init__(self, advice_items: list[str] | None = None) -> None:
        self._items = list(advice_items or ADVICE_LIST)

    def random_advice(self) -> str:
        return random.choice(self._items)
