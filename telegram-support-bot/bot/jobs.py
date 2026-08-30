"""Scheduled jobs (currently the daily morning greeting)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram.ext import Application, ContextTypes

from bot.config import Settings
from bot.exceptions import ExternalAPIError
from bot.handlers.common import notifications_of

logger = logging.getLogger(__name__)

MORNING_TEXT = (
    "🌞 Доброе утро, коллеги! Желаем продуктивного дня и поменьше проблем с системой! 😊"
)


async def morning_greeting(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Post a short greeting to the support group."""
    try:
        await notifications_of(context).notify_group(context.bot, MORNING_TEXT)
    except ExternalAPIError:
        logger.error("Morning greeting was not delivered")


def schedule_jobs(application: Application, settings: Settings) -> None:
    """Register recurring jobs if JobQueue is installed."""
    job_queue = application.job_queue
    if job_queue is None:
        logger.warning("JobQueue is unavailable; install python-telegram-bot[job-queue]")
        return
    try:
        morning = datetime.strptime(settings.morning_time_utc, "%H:%M").time().replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        logger.error("Invalid MORNING_TIME_UTC=%r, expected HH:MM", settings.morning_time_utc)
        return
    job_queue.run_daily(morning_greeting, time=morning, days=tuple(range(7)))
    logger.info("Morning greeting scheduled at %s UTC", settings.morning_time_utc)
