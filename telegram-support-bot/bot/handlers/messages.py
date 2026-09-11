"""Incoming text messages (not slash-commands)."""

from __future__ import annotations

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.data.phrases import BOT_INFO_TEXT
from bot.exceptions import DatabaseError, ExternalAPIError
from bot.handlers.common import (
    advice_of, ai_of, matcher_of, notifications_of,
    repo_of, safe_reply, settings_of,
)

logger = logging.getLogger(__name__)

# Парсим проблему из эскалации: "Сообщение: {text}"
_ESCALATION_RE = re.compile(r"Сообщение:\s*(.+)", re.DOTALL)


async def _try_learn_from_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Если админ отвечает реплаем на сообщение бота — сохраняем решение.

    Возвращает True, если апдейт обработан (и дальше идти не нужно).
    """
    message = update.message
    reply_to = message.reply_to_message
    if reply_to is None:
        return False

    # Только сообщения от НАШЕГО бота
    me = await context.bot.get_me()
    if reply_to.from_user is None or reply_to.from_user.id != me.id:
        return False

    # Только админы
    settings = settings_of(context)
    user = message.from_user
    if not user or not settings.is_admin(user.id):
        return False

    # Достаём текст проблемы из исходного сообщения бота
    original = reply_to.text or ""
    match = _ESCALATION_RE.search(original)
    if not match:
        return False

    problem_text = match.group(1).strip()
    solution_text = (message.text or "").strip()

    # Отсеиваем "ок", "принял", короткие фразы
    if len(solution_text) < 15 or solution_text.startswith("/"):
        return False
    if len(problem_text) < 5:
        return False

    try:
        repo_of(context).add_solution(problem_text, solution_text)
        await safe_reply(
            message,
            "🧠 Спасибо! Я запомнил это решение и буду выдавать его автоматически "
            "при похожих проблемах.",
        )
        logger.info("Auto-learned solution for: %s", problem_text[:60])
    except DatabaseError:
        await safe_reply(message, "⚠️ Не удалось сохранить решение в базу знаний.")
    return True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route free-text messages: auto-learn, RAG, help phrases, keywords."""
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

    # 1) АВТООБУЧЕНИЕ: админ ответил реплаем на сообщение бота?
    if message.reply_to_message:
        if await _try_learn_from_reply(update, context):
            return
        return  # другие реплаи игнорируем

    if text.startswith("/"):
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
                context.bot, username=username, body=text, kind="help",
            )
        except ExternalAPIError:
            await safe_reply(message, "⚠️ Не удалось отправить уведомление. Попробуйте позже.")
        return

    if matcher.matches_keyword(text):
        logger.info("Keyword match — trying RAG")

        # 🧠 RAG: ищем готовое решение в базе знаний
        try:
            solutions = repo_of(context).search_solutions(text, min_matches=1, limit=3)
        except DatabaseError:
            solutions = []

        ai = ai_of(context)
        if solutions and ai.enabled:
            logger.info("RAG: found %s solutions", len(solutions))
            try:
                top_id, _ = solutions[0]
                answer = ai.answer_with_context(text, [sol for _, sol in solutions])
                keyboard = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("👍 Помогло", callback_data=f"kb_helpful:{top_id}"),
                        InlineKeyboardButton("👎 Не помогло", callback_data=f"kb_nothelpful:{top_id}"),
                    ]]
                )
                await message.reply_text(f"✅ {answer}", reply_markup=keyboard)
                return
            except ExternalAPIError:
                logger.warning("RAG AI failed, falling back to advice")

        # Fallback: обычная логика (ИИ или рандомный совет + кнопки)
        context.user_data["last_problem_text"] = text
        advice = ""
        if ai.enabled:
            try:
                advice = ai.ask(text)
            except ExternalAPIError:
                advice = advice_of(context).random_advice()
        else:
            advice = advice_of(context).random_advice()

        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Помогло", callback_data="advice_helped"),
                InlineKeyboardButton("❌ Не помогло", callback_data="advice_not_helped"),
            ]]
        )
        try:
            await message.reply_text(
                f"🧠 Совет по решению:\n{advice}\n\n"
                "Если совет помог, нажмите «Помогло». Если нет — мы отправим запрос аналитику.",
                reply_markup=keyboard,
            )
        except TelegramError:
            logger.exception("Failed to send advice reply")
        return
