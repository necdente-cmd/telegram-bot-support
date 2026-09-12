"""Application bootstrap. Tables are ensured via SQLAlchemy metadata (no Alembic at runtime)."""

from __future__ import annotations

import logging

from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from bot.config import Settings, get_settings
from bot.data.phrases import DEFAULT_RESPONSIBLE, INITIAL_KEYWORDS
from bot.db.engine import create_all_tables, ensure_columns, init_engine
from bot.db.repository import SupportRepository
from bot.domain.matching import AdviceService, MessageMatcher
from bot.handlers.callbacks import advice_callback, kb_rating_callback
from bot.handlers.errors import on_error
from bot.handlers.messages import handle_message
from bot.health import start_health_server
from bot.jobs import schedule_jobs
from bot.logging_setup import configure_logging
from bot.services.ai_service import AiService
from bot.services.command_registry import CommandRegistry
from bot.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


async def _post_init(application: Application) -> None:
    registry: CommandRegistry = application.bot_data["command_registry"]
    await application.bot.set_my_commands(registry.as_bot_commands())
    logger.info("Telegram command menu updated")


def build_application(settings: Settings) -> Application:
    """Wire handlers, services, and the Telegram Application."""
    # 1. Создаём engine
    init_engine(settings)
    # 2. Создаём таблицы и колонки
    try:
        create_all_tables()
        ensure_columns()
        logger.info("Database tables ensured via SQLAlchemy metadata")
    except Exception as exc:
        logger.exception("Failed to create tables: %s", exc)

    # 3. Сервисы
    repository = SupportRepository()
    repository.seed_if_empty(INITIAL_KEYWORDS, DEFAULT_RESPONSIBLE)
    keywords = repository.list_keywords()
    matcher = MessageMatcher(keywords)
    logger.info("Loaded %s keywords", len(keywords))

    application = (
        Application.builder()
        .token(settings.bot_token)
        .post_init(_post_init)
        .build()
    )

    application.bot_data["settings"] = settings
    application.bot_data["repository"] = repository
    application.bot_data["matcher"] = matcher
    application.bot_data["advice"] = AdviceService()
    application.bot_data["notifications"] = NotificationService(settings, repository)
    application.bot_data["ai"] = AiService(settings)

    # 4. Обработчики
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message), group=0
    )

    # 5. Callback'и кнопок
    application.add_handler(
        CallbackQueryHandler(
            advice_callback, pattern=r"^(advice_helped|advice_not_helped)$"
        ),
        group=2,
    )
    application.add_handler(
        CallbackQueryHandler(
            kb_rating_callback, pattern=r"^kb_(helpful|nothelpful):\d+$"
        ),
        group=2,
    )

    # 6. Команды из commands.yaml
    registry = CommandRegistry(settings)
    registry.register(application)
    application.bot_data["command_registry"] = registry

    application.add_error_handler(on_error)
    schedule_jobs(application, settings)
    return application


def run() -> None:
    """CLI entry: configure logging, start health server, build the app, start polling."""
    settings = get_settings()
    configure_logging(settings)
    logger.info("Starting support bot")
    start_health_server()
    application = build_application(settings)
    # drop_pending_updates=False — не теряем сообщения при перезапуске
    application.run_polling(drop_pending_updates=False)
