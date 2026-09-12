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

    data = query.data or ""
    try:
        if data == "advice_helped":
            # Кнопки исчезают, окно "Спасибо"
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except TelegramError:
                pass
            try:
                await query.answer("✅ Отлично! Рады, что помогли.", show_alert=True)
            except TelegramError:
                pass
            return

        if data == "advice_not_helped":
            # Кнопки исчезают, эскалация
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except TelegramError:
                pass
            try:
                await query.answer("🔄 Передаю ответственному...", show_alert=True)
            except TelegramError:
                pass
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
                logger.error("Escalation after 'not helped' failed")
            return
    except TelegramError:
        logger.exception("Failed to edit callback message")


async def kb_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Оценка RAG-ответа.

    👍 Помогло    → +1 к рейтингу, кнопки исчезают, окно «Спасибо».
    👎 Не помогло → -1 к рейтингу, кнопки исчезают, ЭСКАЛАЦИЯ ответственному.
    """
    query = update.callback_query
    if query is None:
        logger.warning("kb_rating_callback: query is None")
        return

    logger.info(
        "kb_rating_callback: data=%s user_id=%s",
        query.data,
        query.from_user.id if query.from_user else None,
    )

    data = query.data or ""
    try:
        action, _, kb_id_str = data.partition(":")
        kb_id = int(kb_id_str)
    except (ValueError, AttributeError) as exc:
        logger.error("Failed to parse callback data '%s': %s", data, exc)
        try:
            await query.answer("Ошибка обработки кнопки", show_alert=True)
        except TelegramError:
            pass
        return

    user_id = query.from_user.id if query.from_user else 0
    if user_id == 0:
        return

    try:
        if action == "kb_helpful":
            # 👍 Помогло
            new_rating = repo_of(context).rate_kb(kb_id, +1)

            # 1. Убираем клавиатуру (кнопки исчезают)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except TelegramError as exc:
                logger.warning("Failed to remove keyboard: %s", exc)

            # 2. Всплывающее окно
            try:
                await query.answer(
                    f"✅ Спасибо! Текущий рейтинг решения: {new_rating}",
                    show_alert=True,
                )
            except TelegramError:
                pass

            logger.info("KB #%s rated +1 by user %s, new rating %s", kb_id, user_id, new_rating)

        elif action == "kb_nothelpful":
            # 👎 Не помогло
            new_rating = repo_of(context).rate_kb(kb_id, -1)

            # 1. Убираем клавиатуру (кнопки исчезают)
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except TelegramError as exc:
                logger.warning("Failed to remove keyboard: %s", exc)

            # 2. Окно
            if new_rating == -999:
                try:
                    await query.answer(
                        "🗑️ Решение удалено из базы как нерабочее.",
                        show_alert=True,
                    )
                except TelegramError:
                    pass
                logger.info("KB #%s deleted after too many dislikes", kb_id)
                return

            try:
                await query.answer(
                    "🔄 Спасибо! Передаю ответственному...",
                    show_alert=True,
                )
            except TelegramError:
                pass
            logger.info("KB #%s rated -1 by user %s, new rating %s", kb_id, user_id, new_rating)

            # 3. Эскалация ответственному
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
