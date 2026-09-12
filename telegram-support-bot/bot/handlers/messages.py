"""Incoming text messages (not slash-commands)."""

from __future__ import annotations

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.data.i18n import detect_language, t
from bot.data.phrases import BOT_INFO_TEXT
from bot.exceptions import DatabaseError, ExternalAPIError
from bot.handlers.common import (
    advice_of, ai_of, matcher_of, notifications_of,
    repo_of, safe_reply, settings_of,
)

logger = logging.getLogger(__name__)

_ESCALATION_RE = re.compile(r"Сообщение:\s*(.+)", re.DOTALL)
TG_MAX = 4000  # Чуть меньше лимита Telegram (4096)


def _remember_problem(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    if "last_problem_by_chat" not in context.bot_data:
        context.bot_data["last_problem_by_chat"] = {}
    context.bot_data["last_problem_by_chat"][chat_id] = text


def _get_last_problem(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> str | None:
    return context.bot_data.get("last_problem_by_chat", {}).get(chat_id)


async def _send_long(message, text: str) -> None:
    """Отправляет длинный ответ, разбивая на части по лимиту Telegram."""
    if not text:
        return
    if len(text) <= TG_MAX:
        await message.reply_text(text)
        logger.info("AI answer sent (len=%s)", len(text))
        return
    parts = [text[i:i + TG_MAX] for i in range(0, len(text), TG_MAX)]
    for part in parts:
        await message.reply_text(part)
    logger.info("AI answer sent in %s parts (total=%s)", len(parts), len(text))


async def _try_learn_from_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    message = update.message
    reply_to = message.reply_to_message
    if reply_to is None:
        return False

    me = await context.bot.get_me()
    if reply_to.from_user is None or reply_to.from_user.id != me.id:
        return False

    settings = settings_of(context)
    user = message.from_user
    if not user or not settings.is_admin(user.id):
        return False

    solution_text = (message.text or "").strip()
    if len(solution_text) < 15 or solution_text.startswith("/"):
        return False

    pending = context.bot_data.get("pending_escalations", {})
    problem_text = pending.get(reply_to.message_id, "")

    if not problem_text:
        original = reply_to.text or ""
        match = _ESCALATION_RE.search(original)
        if match:
            problem_text = match.group(1).strip()

    if not problem_text:
        last = _get_last_problem(context, message.chat_id)
        if last:
            problem_text = last

    if not problem_text or len(problem_text) < 5:
        return False

    try:
        repo_of(context).add_solution(problem_text, solution_text)
        await safe_reply(message, "🧠 Спасибо! Я запомнил это решение и буду выдавать его автоматически при похожих проблемах.")
        logger.info("Auto-learned solution for: %s", problem_text[:60])
        if reply_to.message_id in pending:
            del pending[reply_to.message_id]
    except DatabaseError:
        await safe_reply(message, "⚠️ Не удалось сохранить решение в базу знаний.")
    return True


def _extract_text(message) -> str:
    """Извлекает текст из сообщения, включая пересланные."""
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    return ""


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    text = _extract_text(message)
    if not text:
        return

    user = message.from_user
    username = user.username if user else None
    lang = detect_language(text)
    logger.info("Incoming text from %s (chat_id=%s, lang=%s): %s", username, message.chat_id, lang, text[:120])

    try:
        if user and repo_of(context).is_banned(user.id):
            await safe_reply(message, t("banned", lang))
            return
    except DatabaseError:
        logger.error("Ban check failed; allowing message through")

    if message.reply_to_message:
        if await _try_learn_from_reply(update, context):
            return
        return

    if text.startswith("/"):
        return

    settings = settings_of(context)
    matcher = matcher_of(context)

    # 1) Вопросы о боте
    if matcher.mentions_bot(text, settings.bot_username) or matcher.is_about_bot(text):
        await safe_reply(message, BOT_INFO_TEXT)
        return

    # 2) Технические работы
    if matcher.is_technical_works(text):
        await safe_reply(message, t("tech_works", lang))
        return

    # 3) Явный запрос помощи
    if matcher.is_help_request(text):
        logger.info("Help request recognized")
        _remember_problem(context, message.chat_id, text)
        await safe_reply(message, t("help_request", lang))
        if user:
            try:
                repo_of(context).log_message(
                    user_id=user.id, username=username, chat_id=message.chat_id,
                    text=text, matched_kb_id=None, answered_by_rag=0,
                )
            except Exception:
                pass
        try:
            await notifications_of(context).escalate(
                context.bot, username=username, body=text, kind="help", context=context,
            )
        except ExternalAPIError:
            await safe_reply(message, t("notify_failed", lang))
        return

    # 4) Запрос на доработку
    if matcher.is_feature_request(text) and len(text) > 80:
        logger.info("Feature request recognized")
        _remember_problem(context, message.chat_id, text)
        await safe_reply(message, "📝 Принято! Это запрос на доработку системы. Передаю ответственным.")
        try:
            await notifications_of(context).escalate(
                context.bot, username=username, body=text, kind="feature", context=context,
            )
        except ExternalAPIError:
            logger.error("Feature escalation failed")
        return

    # 5) Проблема поддержки → RAG
    is_problem = matcher.is_support_problem(text)
    has_keyword = matcher.matches_keyword(text)

    if is_problem and has_keyword:
        logger.info("Support problem + keyword — trying RAG")
        _remember_problem(context, message.chat_id, text)
        context.user_data["last_problem_text"] = text

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
                        InlineKeyboardButton(t("btn_kb_helpful", lang), callback_data=f"kb_helpful:{top_id}"),
                        InlineKeyboardButton(t("btn_kb_nothelpful", lang), callback_data=f"kb_nothelpful:{top_id}"),
                    ]]
                )
                if len(answer) <= TG_MAX:
                    await message.reply_text(f"✅ {answer}", reply_markup=keyboard)
                else:
                    parts = [answer[i:i + TG_MAX] for i in range(0, len(answer), TG_MAX)]
                    for i, part in enumerate(parts):
                        prefix = "✅ " if i == 0 else ""
                        await message.reply_text(f"{prefix}{part}",
                                                  reply_markup=keyboard if i == 0 else None)
                if user:
                    try:
                        repo_of(context).log_message(
                            user_id=user.id, username=username, chat_id=message.chat_id,
                            text=text, matched_kb_id=top_id, answered_by_rag=1,
                        )
                    except Exception:
                        pass
                return
            except ExternalAPIError:
                logger.warning("RAG AI failed, falling back to advice")

        advice = advice_of(context).random_advice()
        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton(t("btn_helped", lang), callback_data="advice_helped"),
                InlineKeyboardButton(t("btn_not_helped", lang), callback_data="advice_not_helped"),
            ]]
        )
        try:
            await message.reply_text(
                f"{t('advice_header', lang)}\n{advice}\n\n{t('advice_footer', lang)}",
                reply_markup=keyboard,
            )
            if user:
                try:
                    repo_of(context).log_message(
                        user_id=user.id, username=username, chat_id=message.chat_id,
                        text=text, matched_kb_id=None, answered_by_rag=0,
                    )
                except Exception:
                    pass
        except TelegramError:
            logger.exception("Failed to send advice reply")
        return

    # 6) Просто вопрос / болтовня
    # В группе — молчим (защита от шума). В личке — отвечаем.
    is_private = message.chat.type == ChatType.PRIVATE
    ai = ai_of(context)

    if is_private and ai.enabled and len(text) > 2:
        try:
            answer = ai.ask(text)
            if not answer:
                return
            await _send_long(message, answer)
            return
        except TelegramError as exc:
            logger.error("Telegram error while sending AI answer: %s", exc)
        except ExternalAPIError:
            logger.warning("AI ask failed")
    else:
        logger.info("General question in group — ignored (use /ask)")

    return
