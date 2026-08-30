"""Helpers shared by Telegram handlers."""

from __future__ import annotations

import logging

from telegram import Message, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.config import Settings
from bot.db.repository import SupportRepository
from bot.domain.matching import AdviceService, MessageMatcher
from bot.services.ai_service import AiService
from bot.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def settings_of(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.bot_data["settings"]


def repo_of(context: ContextTypes.DEFAULT_TYPE) -> SupportRepository:
    return context.bot_data["repository"]


def matcher_of(context: ContextTypes.DEFAULT_TYPE) -> MessageMatcher:
    return context.bot_data["matcher"]


def advice_of(context: ContextTypes.DEFAULT_TYPE) -> AdviceService:
    return context.bot_data["advice"]


def notifications_of(context: ContextTypes.DEFAULT_TYPE) -> NotificationService:
    return context.bot_data["notifications"]


def ai_of(context: ContextTypes.DEFAULT_TYPE) -> AiService:
    return context.bot_data["ai"]


async def safe_reply(message: Message | None, text: str, **kwargs) -> None:
    """Reply to a message, logging Telegram API failures instead of crashing."""
    if message is None:
        return
    try:
        await message.reply_text(text, **kwargs)
    except TelegramError:
        logger.exception("Failed to reply in chat_id=%s", message.chat_id)


def user_id_of(update: Update) -> int | None:
    user = update.effective_user
    return user.id if user else None
