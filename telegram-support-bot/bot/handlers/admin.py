"""Admin-only slash-command handlers (also gated in CommandRegistry)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.exceptions import DatabaseError
from bot.handlers.common import matcher_of, repo_of, safe_reply

logger = logging.getLogger(__name__)


async def add_keyword_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a phrase that should trigger troubleshooting advice."""
    if not context.args:
        await safe_reply(update.message, "Укажите ключевое слово: /add_keyword система не работает")
        return
    keyword = " ".join(context.args).strip().lower()
    if not keyword:
        await safe_reply(update.message, "Некорректное ключевое слово.")
        return
    try:
        repo_of(context).add_keyword(keyword)
        matcher_of(context).replace_keywords(repo_of(context).list_keywords())
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось сохранить ключевое слово.")
        return
    await safe_reply(update.message, f"✅ Ключевое слово «{keyword}» добавлено.")


async def remove_keyword_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a keyword phrase."""
    if not context.args:
        await safe_reply(
            update.message, "Укажите ключевое слово: /remove_keyword система не работает"
        )
        return
    keyword = " ".join(context.args).strip().lower()
    try:
        removed = repo_of(context).remove_keyword(keyword)
        matcher_of(context).replace_keywords(repo_of(context).list_keywords())
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось удалить ключевое слово.")
        return
    if not removed:
        await safe_reply(update.message, f"Ключевое слово «{keyword}» не найдено.")
        return
    await safe_reply(update.message, f"✅ Ключевое слово «{keyword}» удалено.")


async def add_responsible_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a Telegram username (without requiring @) to the escalation list."""
    if not context.args:
        await safe_reply(update.message, "Укажите юзернейм: /add_responsible @username")
        return
    username = context.args[0].lstrip("@").strip()
    if not username:
        await safe_reply(update.message, "Некорректный юзернейм.")
        return
    try:
        repo_of(context).add_responsible(username)
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось добавить ответственного.")
        return
    await safe_reply(update.message, f"✅ @{username} добавлен в список ответственных.")


async def remove_responsible_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a username from the escalation list."""
    if not context.args:
        await safe_reply(update.message, "Укажите юзернейм: /remove_responsible @username")
        return
    username = context.args[0].lstrip("@").strip()
    try:
        removed = repo_of(context).remove_responsible(username)
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось удалить ответственного.")
        return
    if not removed:
        await safe_reply(update.message, f"@{username} не найден в списке.")
        return
    await safe_reply(update.message, f"✅ @{username} удалён из списка ответственных.")


async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user by numeric Telegram ID."""
    if not context.args:
        await safe_reply(update.message, "Укажите ID пользователя: /ban_user 123456789")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await safe_reply(update.message, "Некорректный ID.")
        return
    try:
        repo_of(context).ban_user(target_id, reason="Забанен администратором")
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось забанить пользователя.")
        return
    await safe_reply(update.message, f"✅ Пользователь {target_id} забанен.")


async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a ban by numeric Telegram ID."""
    if not context.args:
        await safe_reply(update.message, "Укажите ID пользователя: /unban_user 123456789")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await safe_reply(update.message, "Некорректный ID.")
        return
    try:
        removed = repo_of(context).unban_user(target_id)
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось разбанить пользователя.")
        return
    if not removed:
        await safe_reply(update.message, f"Пользователь {target_id} не был в бан-листе.")
        return
    await safe_reply(update.message, f"✅ Пользователь {target_id} разбанен.")


async def list_banned_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List currently banned user IDs."""
    try:
        rows = repo_of(context).list_banned()
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось прочитать бан-лист.")
        return
    if not rows:
        await safe_reply(update.message, "Забаненных пользователей нет.")
        return
    lines = ["🚫 Забаненные пользователи:"]
    for row in rows:
        stamp = row.banned_at.strftime("%Y-%m-%d %H:%M") if row.banned_at else "?"
        reason = row.reason or "не указана"
        lines.append(f"ID: {row.user_id} (причина: {reason}, забанен: {stamp})")
    await safe_reply(update.message, "\n".join(lines))


async def reload_commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-read commands.yaml and re-bind slash-command handlers without restarting."""
    registry = context.bot_data.get("command_registry")
    if registry is None:
        await safe_reply(update.message, "❌ Реестр команд недоступен.")
        return
    try:
        count = await registry.reload(context.application)
    except Exception:
        logger.exception("Command reload failed")
        await safe_reply(update.message, "❌ Не удалось перезагрузить команды. Смотрите логи.")
        return
    await safe_reply(update.message, f"✅ Команды перезагружены ({count} шт.).")
