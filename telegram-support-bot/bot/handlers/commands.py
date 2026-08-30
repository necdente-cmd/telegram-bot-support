"""Public slash-command handlers (reloaded via CommandRegistry)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.data.phrases import BOT_INFO_TEXT
from bot.exceptions import DatabaseError, ExternalAPIError
from bot.handlers.common import ai_of, repo_of, safe_reply, settings_of

logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the bot capabilities and command list."""
    await safe_reply(update.message, BOT_INFO_TEXT)


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Forward a short question to the configured AI backend."""
    message = update.message
    ai = ai_of(context)
    settings = settings_of(context)

    if not ai.enabled:
        await safe_reply(message, "❌ ИИ не настроен.")
        return
    if not context.args:
        await safe_reply(message, "❓ Напишите вопрос после команды: /ask ваш вопрос")
        return

    question = " ".join(context.args)
    if len(question) > settings.ai_question_max_length:
        await safe_reply(
            message,
            f"⚠️ Вопрос слишком длинный (макс. {settings.ai_question_max_length} символов).",
        )
        return

    await safe_reply(message, "🤔 Думаю...")
    try:
        answer = ai.ask(question)
        await safe_reply(message, answer)
    except ExternalAPIError:
        await safe_reply(message, "❌ Извините, произошла ошибка при обращении к ИИ.")
    except TelegramError:
        logger.exception("Failed to send AI answer")


async def list_keywords_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all keywords that trigger advice replies."""
    try:
        keywords = repo_of(context).list_keywords()
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось прочитать ключевые слова.")
        return
    if not keywords:
        await safe_reply(update.message, "Список ключевых слов пуст.")
        return
    lines = "\n".join(f"• {word}" for word in keywords)
    await safe_reply(update.message, f"📋 Ключевые слова:\n{lines}")


async def list_responsible_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show usernames that are mentioned on escalation."""
    try:
        users = repo_of(context).list_responsible()
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось прочитать список ответственных.")
        return
    if not users:
        await safe_reply(update.message, "Список ответственных пуст.")
        return
    lines = "\n".join(f"@{name}" for name in users)
    await safe_reply(update.message, f"📋 Список ответственных:\n{lines}")
