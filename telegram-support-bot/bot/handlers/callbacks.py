"""Inline-button callbacks for advice feedback and KB rating."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.exceptions import DatabaseError, ExternalAPIError
from bot.handlers.common import notifications_of, repo_of

logger = logging.getLogger(__name__)


async def advice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle «helped» / «did not help» buttons under a fallback advice."""
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
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("✅ Отлично! Рады, что помогли.", show_alert=False)
            return
        if data == "advice_not_helped":
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("🔄 Передаю ответственному...", show_alert=False)
            user = query.from_user
            problem = str(context.user_data.get("last_problem_text", ""))
            try:
                await notifications_of(context).escalate(
                    context.bot,
                    username=user.username if user else None,
                    body=problem,
                    kind="advice",
                    context=context,
                )
            except ExternalAPIError:
                logger.error("Escalation after 'not helped' failed")
            return
    except TelegramError:
        logger.exception("Failed to edit callback message")


async def kb_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Оценка RAG-ответа.

    👍 = +1 к рейтингу записи
    👎 = -1 к рейтингу + эскалация ответственному (для автообучения)
    При рейтинге <= -3 запись удаляется.
    """
    query = update.callback_query
    if query is None:
        return

    try:
        await query.answer()
    except TelegramError:
        logger.exception("Failed to answer callback query")

    data = query.data or ""
    try:
        action, _, kb_id_str = data.partition(":")
        kb_id = int(kb_id_str)
    except (ValueError, AttributeError):
        return

    try:
        if action == "kb_helpful":
            new_rating = repo_of(context).rate_kb(kb_id, +1)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.answer("✅ Спасибо! Решение получило +1", show_alert=False)
            logger.info("KB #%s rated +1, new rating %s", kb_id, new_rating)

        elif action == "kb_nothelpful":
            new_rating = repo_of(context).rate_kb(kb_id, -1)
            await query.edit_message_reply_markup(reply_markup=None)

            if new_rating == -999:
                await query.answer(
                    "🗑️ Спасибо! Решение удалено из базы как нерабочее.",
                    show_alert=False,
                )
                logger.info("KB #%s deleted after too many dislikes", kb_id)
            else:
                await query.answer("🔄 Передаю ответственному...", show_alert=False)
                logger.info("KB #%s rated -1, new rating %s", kb_id, new_rating)

            # Отправляем эскалацию в группу
            user = query.from_user
            # Пробуем достать текст проблемы из user_data, потом из bot_data
            problem = str(context.user_data.get("last_problem_text", ""))
            if not problem:
                problem = context.bot_data.get("last_problem_by_chat", {}).get(
                    query.message.chat_id, ""
                )
            if not problem:
                problem = "(текст проблемы не сохранён)"

            try:
                await notifications_of(context).escalate(
                    context.bot,
                    username=user.username if user else None,
                    body=problem,
                    kind="advice",
                    context=context,
                )
            except ExternalAPIError:
                logger.error("Escalation after 'not helpful' failed")

    except DatabaseError:
        await query.answer("⚠️ Ошибка при сохранении оценки", show_alert=True)
        return
