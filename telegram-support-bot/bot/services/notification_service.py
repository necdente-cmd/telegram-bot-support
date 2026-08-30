"""Telegram notifications to the support group."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.error import RetryAfter, TelegramError, TimedOut

from bot.config import Settings
from bot.db.repository import SupportRepository
from bot.exceptions import ExternalAPIError

logger = logging.getLogger(__name__)


class NotificationService:
    """Send escalation messages to the configured group chat."""

    def __init__(self, settings: Settings, repository: SupportRepository) -> None:
        self._settings = settings
        self._repository = repository

    async def notify_group(self, bot: Bot, text: str) -> None:
        """Send a raw message to GROUP_CHAT_ID."""
        try:
            await bot.send_message(chat_id=self._settings.group_chat_id, text=text)
        except RetryAfter as exc:
            logger.warning("Telegram flood wait %ss while notifying group", exc.retry_after)
            raise ExternalAPIError("Telegram rate-limited the bot") from exc
        except TimedOut as exc:
            logger.error("Telegram timeout while notifying group")
            raise ExternalAPIError("Telegram timed out") from exc
        except TelegramError as exc:
            logger.exception("Telegram error while notifying group: %s", exc)
            raise ExternalAPIError("Could not send Telegram message") from exc

    async def escalate(
        self,
        bot: Bot,
        *,
        username: str | None,
        body: str,
        kind: str,
    ) -> None:
        """Mention responsible users about a help request or failed advice."""
        display = f"@{username}" if username else "без юзернейма"
        try:
            responsible = self._repository.list_responsible()
        except Exception:
            logger.exception("Could not load responsible users for escalation")
            await self.notify_group(
                bot,
                "⚠️ Не удалось прочитать список ответственных из базы данных.",
            )
            return

        if not responsible:
            await self.notify_group(
                bot,
                "⚠️ Нет назначенных ответственных. Сообщение не отправлено.",
            )
            return

        mentions = " ".join(f"@{user}" for user in responsible)
        if kind == "help":
            header = f"⚠️ Пользователь {display} запросил помощь."
        else:
            header = f"⚠️ Пользователь {display} не смог решить проблему."
        await self.notify_group(bot, f"{header}\nСообщение: {body}\nОтветственные: {mentions}")
