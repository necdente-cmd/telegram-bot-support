"""Inline-button callbacks for advice feedback."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.exceptions import ExternalAPIError
from bot.handlers.common import notifications_of

logger = logging.getLogger(__name__)


async def advice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle «helped» / «did not help» buttons under an advice message."""
    query = update.callback_query
    if query is None:
        return

    try:
        await query.answer()
    except TelegramError:
        logger.exception("Failed to answer callback query")

    data = query.data or ""
    try:
        if data == "advice_helped":
            await query.edit_message_text("✅ Отлично! Рады, что помогли.")
            return
        if data == "advice_not_helped":
            await query.edit_message_text(
                "🔄 Ваш запрос принят. Сообщение отправлено аналитику системы."
            )
            user = query.from_user
            try:
                await notifications_of(context).escalate(
                    context.bot,
                    username=user.username if user else None,
                    body=str(context.user_data.get("last_problem_text", "")),
                    kind="advice",
                )
            except ExternalAPIError:
                logger.error("Escalation after 'not helped' failed")
            return
    except TelegramError:
        logger.exception("Failed to edit callback message")
