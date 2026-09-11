"""Scheduled jobs: morning greeting, daily report, auto-close."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram.ext import Application, ContextTypes

from bot.config import Settings
from bot.exceptions import ExternalAPIError
from bot.handlers.common import notifications_of, repo_of

logger = logging.getLogger(__name__)

MORNING_TEXT = "🌞 Доброе утро, коллеги! Желаем продуктивного дня и поменьше проблем с системой! 😊"


async def morning_greeting(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        await notifications_of(context).notify_group(context.bot, MORNING_TEXT)
    except ExternalAPIError:
        logger.error("Morning greeting was not delivered")


async def daily_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отчёт за сутки."""
    try:
        repo = repo_of(context)
    except Exception:
        return
    try:
        stats = repo.get_daily_stats(hours=24)
    except Exception as exc:
        logger.error("Failed to get daily stats: %s", exc)
        return

    text = (
        "📊 <b>Отчёт за сутки</b>\n\n"
        f"💬 Всего сообщений-проблем: <b>{stats['total']}</b>\n"
        f"✅ Решено через RAG: <b>{stats['rag']}</b>\n"
        f"👤 Передано ответственным: <b>{stats['escalated']}</b>\n"
        f"📚 Новых записей в базе: <b>{stats['new_kb']}</b>\n"
        f"💡 Обратной связи: <b>{stats['feedback']}</b>\n"
    )
    try:
        await notifications_of(context).notify_group(context.bot, text)
    except ExternalAPIError:
        logger.error("Daily report was not delivered")


def _parse_hhmm(value: str):
    return datetime.strptime(value, "%H:%M").time().replace(tzinfo=timezone.utc)


def schedule_jobs(application: Application, settings: Settings) -> None:
    job_queue = application.job_queue
    if job_queue is None:
        logger.warning("JobQueue is unavailable; install python-telegram-bot[job-queue]")
        return

    try:
        morning = _parse_hhmm(settings.morning_time_utc)
        job_queue.run_daily(morning_greeting, time=morning, days=tuple(range(7)))
        logger.info("Morning greeting scheduled at %s UTC", settings.morning_time_utc)
    except ValueError:
        logger.error("Invalid MORNING_TIME_UTC=%r", settings.morning_time_utc)

    try:
        report_time = _parse_hhmm(settings.daily_report_time_utc)
        job_queue.run_daily(daily_report, time=report_time, days=tuple(range(7)))
        logger.info("Daily report scheduled at %s UTC", settings.daily_report_time_utc)
    except ValueError:
        logger.error("Invalid DAILY_REPORT_TIME_UTC=%r", settings.daily_report_time_utc)
