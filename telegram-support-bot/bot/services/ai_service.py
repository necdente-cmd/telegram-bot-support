"""DeepSeek / OpenAI-compatible assistant client."""

from __future__ import annotations

import logging
import re

from openai import APIError, APITimeoutError, OpenAI, RateLimitError

from bot.config import Settings
from bot.exceptions import ExternalAPIError

logger = logging.getLogger(__name__)

_MARKDOWN_PATTERNS = (
    (re.compile(r"\*\*(.*?)\*\*", re.DOTALL), r"\1"),
    (re.compile(r"\*(.*?)\*", re.DOTALL), r"\1"),
    (re.compile(r"_(.*?)_", re.DOTALL), r"\1"),
    (re.compile(r"#{1,6}\s?"), ""),
    (re.compile(r"`(.*?)`", re.DOTALL), r"\1"),
    (re.compile(r"\[(.*?)\]\(.*?\)", re.DOTALL), r"\1"),
)

_LANGUAGE_INSTRUCTION = (
    "ЯЗЫК ОТВЕТА: определяй язык вопроса и отвечай на том же языке. "
    "Если вопрос на русском — отвечай на русском. "
    "Если вопрос на кыргызском — отвечай на кыргызском. "
    "НИКОГДА не смешивай языки в одном ответе."
)

_SYSTEM_CONTEXT = (
    "Ты — технический эксперт поддержки медицинской информационной системы "
    "«Sanarip Clinic» (Кыргызская Республика).\n\n"
    "СИСТЕМА включает модули: Амбулаторная карта, Стационарная карта, Справки "
    "(083/у, 086/у, 095/у, 026/у), ЛВН, Регистры (СД, ГВГ, ЖРВ), МСЭК/РВКК/ВКК, "
    "Партограмма, еСОМу, КСФ, ЭМК, Аудит МКАБ, ЕСИ/ОЭП.\n\n"
    "КОНТЕКСТ: «база», «система», «программа», «сайт», «МИС» = Sanarip Clinic.\n"
)


def strip_markdown(text: str) -> str:
    """Убирает Markdown-разметку (для не-HTML отправки)."""
    cleaned = text
    for pattern, replacement in _MARKDOWN_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned.replace("*", "")


class AiService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: OpenAI | None = None
        if settings.deepseek_api_key:
            try:
                self._client = OpenAI(
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_base_url,
                    timeout=30.0,
                )
                logger.info("AI client initialized (base_url=%s)", settings.deepseek_base_url)
            except Exception:
                logger.exception("Failed to initialize AI client")
                self._client = None
        else:
            logger.warning("DEEPSEEK_API_KEY is not set; /ask is disabled")

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def ask(self, question: str) -> str:
        """Общий вопрос — Markdown-ответ."""
        if self._client is None:
            raise ExternalAPIError("AI is not configured")
        try:
            response = self._client.chat.completions.create(
                model=self._settings.ai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — технический ассистент поддержки сотрудников "
                            "медицинских организаций Кыргызстана. "
                            "Отвечай дружелюбно, но по делу. "
                            "Используй **жирный** для важного и `код` для полей. "
                            f"{_SYSTEM_CONTEXT}\n{_LANGUAGE_INSTRUCTION}"
                        ),
                    },
                    {"role": "user", "content": question},
                ],
            )
        except RateLimitError as exc:
            raise ExternalAPIError("AI rate limit exceeded") from exc
        except APITimeoutError as exc:
            raise ExternalAPIError("AI request timed out") from exc
        except APIError as exc:
            raise ExternalAPIError("AI request failed") from exc
        except Exception as exc:
            raise ExternalAPIError("AI request failed") from exc

        choice = response.choices[0].message.content if response.choices else None
        if not choice:
            raise ExternalAPIError("AI returned an empty response")
        return choice.strip()

    def answer_with_context(
        self,
        question: str,
        context_solutions: list[str],
        style: str = "default",
        dialogue_history: list[dict] | None = None,
    ) -> str:
        """RAG-ответ с объединением записей, контекстом диалога и стилем.

        Args:
            question: вопрос пользователя
            context_solutions: список найденных решений (из базы знаний)
            style: "default" | "newbie" | "expert" | "manager"
            dialogue_history: список последних сообщений [{"role": ..., "content": ...}]
        """
        if self._client is None:
            raise ExternalAPIError("AI is not configured")

        # Объединяем найденные записи в блок контекста
        context = "\n\n".join(
            f"Запись {i}:\n{sol}" for i, sol in enumerate(context_solutions, 1)
        )

        # Стиль ответа
        style_rules = {
            "newbie": (
                "СТИЛЬ: подробно, дружелюбно, с путями в меню. "
                "Пользователь — новичок, объясняй по шагам."
            ),
            "expert": (
                "СТИЛЬ: кратко, без пояснений базовых вещей. "
                "Пользователь — опытный, давай только суть."
            ),
            "manager": (
                "СТИЛЬ: с ссылками на нормативные документы и приказы МЗ КР."
            ),
            "default": (
                "СТИЛЬ: дружелюбно, живо, но по делу. "
                "Создавай ощущение диалога с опытным коллегой."
            ),
        }.get(style, "")

        system_prompt = (
            f"{_SYSTEM_CONTEXT}\n"
            f"{style_rules}\n\n"
            "ЗАДАЧА:\n"
            "У тебя есть вопрос пользователя и несколько ВЫДЕРЖЕК из базы знаний.\n\n"
            "ПРАВИЛА:\n"
            "1. Сформулируй ЦЕЛЬНЫЙ ответ, объединив ВСЕ подходящие выдержки "
            "в один связный текст. Не перечисляй их по отдельности.\n"
            "2. Если в выдержках есть пошаговая инструкция — оформи её "
            "нумерованным списком (1. 2. 3.).\n"
            "3. Используй **жирный** для важных слов и `код` для названий "
            "полей и кнопок.\n"
            "4. Указывай точные пути: **Приём → Регистрация → Поиск**.\n"
            "5. Сохраняй ЖИВОЙ, дружелюбный стиль. Начинай с краткого "
            "введения (1 предложение), потом детали.\n"
            "6. Если информации в выдержках НЕ хватает — задай 1 уточняющий "
            "вопрос в конце. Но не выдумывай.\n"
            "7. Максимум 7 предложений / пунктов.\n\n"
            f"{_LANGUAGE_INSTRUCTION}"
        )

        # Собираем сообщения: system + история + user
        messages = [{"role": "system", "content": system_prompt}]

        # Добавляем историю диалога (если есть)
        if dialogue_history:
            messages.extend(dialogue_history[-5:])  # последние 5

        messages.append({
            "role": "user",
            "content": (
                f"Вопрос пользователя: {question}\n\n"
                f"Найденные выдержки из базы знаний:\n{context}"
            ),
        })

        try:
            response = self._client.chat.completions.create(
                model=self._settings.ai_model,
                messages=messages,
            )
            choice = response.choices[0].message.content if response.choices else None
            if not choice:
                raise ExternalAPIError("AI returned an empty response")
            return choice.strip()
        except ExternalAPIError:
            raise
        except Exception as exc:
            logger.exception("RAG AI request failed")
            raise ExternalAPIError("AI request failed") from exc
