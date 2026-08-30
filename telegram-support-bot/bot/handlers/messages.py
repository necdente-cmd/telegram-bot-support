"""Incoming text messages (not slash-commands)."""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.data.phrases import BOT_INFO_TEXT
from bot.exceptions import DatabaseError, ExternalAPIError
from bot.handlers.common import (
    advice_of,
    matcher_of,
    notifications_of,
    repo_of,
    safe_reply,
    settings_of,
)

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route free-text messages: help phrases, keywords, or bot-info questions."""
    message = update.message
    if message is None or not message.text:
        return

    text = message.text
    user = message.from_user
    username = user.username if user else None
    logger.info("Incoming text from %s (chat_id=%s): %s", username, message.chat_id, text)

    try:
        if user and repo_of(context).is_banned(user.id):
            await safe_reply(message, "⛔ Вы забанены.")
            return
    except DatabaseError:
        logger.error("Ban check failed; allowing message through")

    # Ignore replies in threads and anything that looks like a command leftover.
    if message.reply_to_message or text.startswith("/"):
        return

    settings = settings_of(context)
    matcher = matcher_of(context)

    if matcher.mentions_bot(text, settings.bot_username) or matcher.is_about_bot(text):
        await safe_reply(message, BOT_INFO_TEXT)
        return

    if matcher.is_technical_works(text):
        await safe_reply(
            message,
            "🛠 Ведутся технические работы. Пожалуйста, подождите немного.\n"
            "Если проблема останется, обратитесь к ответственному.",
        )
        return

    if matcher.is_help_request(text):
        logger.info("Help request recognized")
        await safe_reply(
            message,
            "🆘 Я вас понял! Сейчас передам сообщение ответственному.\n"
            "Пожалуйста, опишите проблему подробнее, если не сделали этого ранее.",
        )
        try:
            await notifications_of(context).escalate(
                context.bot,
                username=username,
                body=text,
                kind="help",
            )
        except ExternalAPIError:
            await safe_reply(message, "⚠️ Не удалось отправить уведомление. Попробуйте позже.")
        return

    if matcher.matches_keyword(text):
        logger.info("Keyword match recognized")
        context.user_data["last_problem_text"] = text
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Помогло", callback_data="advice_helped"),
                    InlineKeyboardButton("❌ Не помогло", callback_data="advice_not_helped"),
                ]
            ]
        )
        try:
            await message.reply_text(
                f"🧠 Совет по решению:\n{advice_of(context).random_advice()}\n\n"
                "Если совет помог, нажмите «Помогло». Если нет — мы отправим запрос аналитику.",
                reply_markup=keyboard,
            )
        except TelegramError:
            logger.exception("Failed to send advice reply")
        return
