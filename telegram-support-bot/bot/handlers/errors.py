"""Global error handler for the Telegram application."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import ContextTypes

from bot.exceptions import DatabaseError, ExternalAPIError
from bot.handlers.common import safe_reply

logger = logging.getLogger(__name__)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch unhandled exceptions from handlers so polling keeps running."""
    error = context.error
    if isinstance(error, RetryAfter):
        logger.warning("Telegram RetryAfter: wait %ss", error.retry_after)
        return
    if isinstance(error, (TimedOut, NetworkError)):
        logger.error("Telegram network issue: %s", error)
        return
    if isinstance(error, (DatabaseError, ExternalAPIError)):
        logger.error("Application error: %s", error)
    elif isinstance(error, TelegramError):
        logger.error("Telegram API error: %s", error)
    else:
        logger.exception("Unhandled error: %s", error)

    if isinstance(update, Update) and update.effective_message:
        await safe_reply(update.effective_message, "❌ Произошла внутренняя ошибка. Попробуйте позже.")
