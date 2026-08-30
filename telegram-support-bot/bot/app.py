"""Alembic helpers and application bootstrap."""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from bot.config import BASE_DIR, Settings, get_settings
from bot.data.phrases import DEFAULT_RESPONSIBLE, INITIAL_KEYWORDS
from bot.db.engine import init_engine
from bot.db.repository import SupportRepository
from bot.domain.matching import AdviceService, MessageMatcher
from bot.handlers.callbacks import advice_callback
from bot.handlers.errors import on_error
from bot.handlers.messages import handle_message
from bot.jobs import schedule_jobs
from bot.logging_setup import configure_logging
from bot.services.ai_service import AiService
from bot.services.command_registry import CommandRegistry
from bot.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


def run_migrations(settings: Settings) -> None:
    """Apply Alembic migrations up to head (creates tables on a fresh database)."""
    ini_path = BASE_DIR / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"alembic.ini is missing at {ini_path}")
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)
    command.upgrade(cfg, "head")
    logger.info("Database migrations applied")


async def _post_init(application: Application) -> None:
    registry: CommandRegistry = application.bot_data["command_registry"]
    await application.bot.set_my_commands(registry.as_bot_commands())
    logger.info("Telegram command menu updated")


def build_application(settings: Settings) -> Application:
    """Wire handlers, services, and the Telegram Application."""
    init_engine(settings)
    run_migrations(settings)

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

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message), group=0)
    application.add_handler(
        CallbackQueryHandler(advice_callback, pattern=r"^(advice_helped|advice_not_helped)$"),
        group=2,
    )

    registry = CommandRegistry(settings)
    registry.register(application)
    application.bot_data["command_registry"] = registry

    application.add_error_handler(on_error)
    schedule_jobs(application, settings)
    return application


def run() -> None:
    """CLI entry: configure logging, build the app, start polling."""
    settings = get_settings()
    configure_logging(settings)
    logger.info("Starting support bot")
    application = build_application(settings)
    application.run_polling(drop_pending_updates=True)
