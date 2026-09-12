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

# 🎯 Контекст системы, в которой работают сотрудники
_SYSTEM_CONTEXT = (
    "КОНТЕКСТ СИСТЕМЫ:\n"
    "Все сотрудники работают в медицинской информационной системе «Sanarip Clinic» "
    "(также известна как МИС, Санарип, Санприп, Sanarip, түндүк, Түндүк).\n"
    "Когда сотрудник говорит «база», «база данных», «система», «программа», «сайт», «МИС» — "
    "он ВСЕГДА имеет в виду Sanarip Clinic, а не какую-то другую базу данных.\n"
    "Sanarip Clinic включает модули: амбулаторная карта, стационарная карта, "
    "лабораторная система iLAB, электронный больничный (ЛВН), онлайн-запись, "
    "дашборды, отчёты, интеграции с ЦСМ и ГСВ.\n"
)


def strip_markdown(text: str) -> str:
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
        """Общий вопрос — отвечаем с учётом контекста Sanarip Clinic."""
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
                            "медицинских организаций Кыргызстана.\n"
                            f"{_SYSTEM_CONTEXT}\n"
                            f"{_LANGUAGE_INSTRUCTION}"
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
        return strip_markdown(choice)

    def answer_with_context(self, question: str, context_solutions: list[str]) -> str:
        """RAG-ответ на основе базы знаний."""
        if self._client is None:
            raise ExternalAPIError("AI is not configured")

        context = "\n\n".join(f"• {sol}" for sol in context_solutions)

        try:
            response = self._client.chat.completions.create(
                model=self._settings.ai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — технический эксперт поддержки системы «Sanarip Clinic».\n"
                            f"{_SYSTEM_CONTEXT}\n"
                            "Тебе дают вопрос пользователя и выдержки из базы знаний "
                            "(ранее решённые похожие проблемы).\n"
                            "Сформулируй КРАТКИЙ, точный и вежливый ответ на основе этих выдержек.\n"
                            "Если выдержки не помогают — честно скажи, что не знаешь решения.\n"
                            f"{_LANGUAGE_INSTRUCTION}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Вопрос: {question}\n\nИзвестные решения:\n{context}",
                    },
                ],
            )
            choice = response.choices[0].message.content if response.choices else None
            if not choice:
                raise ExternalAPIError("AI returned an empty response")
            return strip_markdown(choice)
        except ExternalAPIError:
            raise
        except Exception as exc:
            raise ExternalAPIError("AI request failed") from exc
