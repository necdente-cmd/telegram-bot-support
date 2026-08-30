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


def strip_markdown(text: str) -> str:
    """Remove common Markdown markers so Telegram shows plain text."""
    cleaned = text
    for pattern, replacement in _MARKDOWN_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned.replace("*", "")


class AiService:
    """Thin wrapper around the OpenAI SDK pointed at DeepSeek (or compatible)."""

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
        """Send a user question to the model and return a plain-text answer."""
        if self._client is None:
            raise ExternalAPIError("AI is not configured")
        try:
            response = self._client.chat.completions.create(
                model=self._settings.ai_model,
                messages=[
                    {"role": "system", "content": "Ты — полезный и информативный ассистент."},
                    {"role": "user", "content": question},
                ],
            )
        except RateLimitError as exc:
            logger.error("AI rate limit: %s", exc)
            raise ExternalAPIError("AI rate limit exceeded") from exc
        except APITimeoutError as exc:
            logger.error("AI timeout: %s", exc)
            raise ExternalAPIError("AI request timed out") from exc
        except APIError as exc:
            logger.error("AI API error: %s", exc)
            raise ExternalAPIError("AI request failed") from exc
        except Exception as exc:
            logger.exception("Unexpected AI error")
            raise ExternalAPIError("AI request failed") from exc

        choice = response.choices[0].message.content if response.choices else None
        if not choice:
            raise ExternalAPIError("AI returned an empty response")
        return strip_markdown(choice)
