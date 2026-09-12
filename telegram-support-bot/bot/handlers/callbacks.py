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

    logger.info("advice_callback: data=%s user=%s", query.data, query.from_user.id if query.from_user else None)

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
    """Оценка RAG-ответа. Защита от дублирования убрана — каждый клик меняет рейтинг."""
    query = update.callback_query
    if query is None:
        logger.warning("kb_rating_callback: query is None")
        return

    logger.info(
        "kb_rating_callback: data=%s user_id=%s",
        query.data,
        query.from_user.id if query.from_user else None,
    )

    # Сразу отвечаем Telegram (убираем "часики")
    try:
        await query.answer()
    except TelegramError as exc:
        logger.warning("Failed to answer callback query: %s", exc)

    data = query.data or ""
    try:
        action, _, kb_id_str = data.partition(":")
        kb_id = int(kb_id_str)
    except (ValueError, AttributeError) as exc:
        logger.error("Failed to parse callback data '%s': %s", data, exc)
        return

    user_id = query.from_user.id if query.from_user else 0
    if user_id == 0:
        logger.warning("user_id is 0 in kb_rating_callback")
        return

    try:
        if action == "kb_helpful":
            new_rating = repo_of(context).rate_kb(kb_id, +1)
            # НЕ убираем клавиатуру — можно нажимать ещё
            try:
                await query.answer(f"✅ Рейтинг решения: {new_rating}", show_alert=False)
            except TelegramError:
                pass
            logger.info("KB #%s rated +1 by user %s, new rating %s", kb_id, user_id, new_rating)

        elif action == "kb_nothelpful":
            new_rating = repo_of(context).rate_kb(kb_id, -1)
            # НЕ убираем клавиатуру — можно нажимать ещё

            if new_rating == -999:
                try:
                    await query.edit_message_reply_markup(reply_markup=None)
                except TelegramError:
                    pass
                try:
                    await query.answer("🗑️ Решение удалено из базы.", show_alert=True)
                except TelegramError:
                    pass
                logger.info("KB #%s deleted after too many dislikes", kb_id)
                return

            try:
                await query.answer(f"❌ Рейтинг решения: {new_rating}", show_alert=False)
            except TelegramError:
                pass
            logger.info("KB #%s rated -1 by user %s, new rating %s", kb_id, user_id, new_rating)

            # Эскалация ответственному
            user = query.from_user
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

    except DatabaseError as exc:
        logger.exception("DB error in kb_rating_callback: %s", exc)
        try:
            await query.answer("⚠️ Ошибка при сохранении оценки", show_alert=True)
        except TelegramError:
            pass
        return
