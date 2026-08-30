"""Dynamic Telegram command registration that can reload without a process restart."""

from __future__ import annotations

import importlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

import yaml
from telegram import BotCommand, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from bot.config import Settings

logger = logging.getLogger(__name__)

HandlerFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]

# Handler group used for slash-commands so they can be removed as a set.
COMMAND_HANDLER_GROUP = 1


@dataclass(frozen=True)
class CommandSpec:
    """One slash-command declared in commands.yaml."""

    name: str
    description: str
    handler: str
    admin_only: bool = False


def _load_specs(path: Path) -> list[CommandSpec]:
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    commands = payload.get("commands") or []
    specs: list[CommandSpec] = []
    for item in commands:
        specs.append(
            CommandSpec(
                name=item["name"],
                description=item.get("description") or item["name"],
                handler=item["handler"],
                admin_only=bool(item.get("admin_only", False)),
            )
        )
    return specs


def _import_handler(dotted_path: str) -> HandlerFn:
    """Import (and reload) a handler function given ``package.module.func``."""
    module_name, _, attr = dotted_path.rpartition(".")
    if not module_name or not attr:
        raise ValueError(f"Invalid handler path: {dotted_path}")
    module = importlib.import_module(module_name)
    module = importlib.reload(module)
    func = getattr(module, attr)
    if not callable(func):
        raise TypeError(f"Handler {dotted_path} is not callable")
    return func


def _require_admin(handler: HandlerFn, settings: Settings) -> HandlerFn:
    @wraps(handler)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        user = update.effective_user
        if not settings.is_admin(user.id if user else None):
            if update.message:
                await update.message.reply_text("⛔ Нет прав.")
            return None
        return await handler(update, context)

    return wrapped


class CommandRegistry:
    """Register slash-commands from YAML and re-bind them at runtime.

    Edit ``commands.yaml`` (and/or handler modules), then run ``/reload_commands``.
    The process stays up; only CommandHandler entries are swapped.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._handlers: list[CommandHandler] = []
        self._specs: list[CommandSpec] = []

    @property
    def specs(self) -> list[CommandSpec]:
        return list(self._specs)

    def load_specs(self) -> list[CommandSpec]:
        path = self._settings.commands_file
        if not path.exists():
            raise FileNotFoundError(f"commands.yaml not found: {path}")
        self._specs = _load_specs(path)
        logger.info("Loaded %s command specs from %s", len(self._specs), path)
        return self._specs

    def unregister(self, application: Application) -> None:
        for handler in self._handlers:
            try:
                application.remove_handler(handler, group=COMMAND_HANDLER_GROUP)
            except ValueError:
                logger.debug("Handler already removed: %s", handler)
        self._handlers.clear()

    def register(self, application: Application) -> None:
        """Attach CommandHandlers. Call unregister() first when reloading."""
        self.load_specs()
        for spec in self._specs:
            func = _import_handler(spec.handler)
            if spec.admin_only:
                func = _require_admin(func, self._settings)
            handler = CommandHandler(spec.name, func)
            application.add_handler(handler, group=COMMAND_HANDLER_GROUP)
            self._handlers.append(handler)
            logger.debug("Registered /%s -> %s", spec.name, spec.handler)

    async def reload(self, application: Application) -> int:
        """Drop and re-add command handlers, then refresh the Telegram command menu."""
        logger.info("Reloading command handlers")
        self.unregister(application)
        self.register(application)
        await application.bot.set_my_commands(self.as_bot_commands())
        return len(self._handlers)

    def as_bot_commands(self) -> list[BotCommand]:
        """Public commands for the Telegram client menu (admin-only hidden)."""
        return [
            BotCommand(spec.name, spec.description)
            for spec in self._specs
            if not spec.admin_only
        ]
