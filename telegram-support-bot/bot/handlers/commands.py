"""Public slash-command handlers (reloaded via CommandRegistry)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.data.i18n import detect_language, t
from bot.data.phrases import BOT_INFO_TEXT
from bot.exceptions import DatabaseError, ExternalAPIError
from bot.handlers.common import ai_of, notifications_of, repo_of, safe_reply, settings_of

logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await safe_reply(update.message, BOT_INFO_TEXT)


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await safe_reply(message, f"⚠️ Вопрос слишком длинный (макс. {settings.ai_question_max_length} символов).")
        return

    await safe_reply(message, "🤔 Думаю...")
    try:
        answer = ai.ask(question)
        await safe_reply(message, answer)
    except ExternalAPIError:
        await safe_reply(message, "❌ Извините, произошла ошибка при обращении к ИИ.")


async def list_keywords_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает топ-5 самых частых проблем за 7 дней."""
    days = 7
    if context.args and context.args[0].isdigit():
        days = int(context.args[0])

    try:
        rows = repo_of(context).get_top_problems(days=days, limit=5)
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось получить статистику.")
        return

    if not rows:
        await safe_reply(update.message, f"📭 За последние {days} дней проблем не было.")
        return

    lines = [f"🔥 Топ-5 частых проблем за {days} дней:", ""]
    for i, (sig, count) in enumerate(rows, 1):
        problem = sig if len(sig) < 80 else sig[:77] + "..."
        lines.append(f"{i}. {problem} — {count} раз")

    await safe_reply(update.message, "\n".join(lines))


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пользователь может оставить обратную связь."""
    message = update.message
    user = message.from_user if message else None

    if not context.args:
        await safe_reply(
            message,
            "💡 Напишите ваше предложение после команды:\n"
            "/feedback Добавьте команду для печати ЛВН",
        )
        return

    text = " ".join(context.args).strip()
    if len(text) < 10:
        await safe_reply(message, "⚠️ Слишком короткое сообщение (минимум 10 символов).")
        return
    if len(text) > 1000:
        await safe_reply(message, "⚠️ Слишком длинное сообщение (максимум 1000 символов).")
        return

    try:
        repo_of(context).add_feedback(
            user_id=user.id if user else 0,
            username=user.username if user else None,
            text=text,
        )
    except DatabaseError:
        await safe_reply(message, "❌ Не удалось сохранить. Попробуйте позже.")
        return

    await safe_reply(message, "🙏 Спасибо! Ваше предложение передано администраторам.")

    # Уведомляем группу
    settings = settings_of(context)
    display = f"@{user.username}" if user and user.username else (user.full_name if user else "аноним")
    notify_text = (
        f"💡 Новая обратная связь от {display}:\n\n"
        f"{text}"
    )
    try:
        await notifications_of(context).notify_group(context.bot, notify_text)
    except ExternalAPIError:
        logger.warning("Could not notify group about feedback")
