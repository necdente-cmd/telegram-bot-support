"""Admin-only slash-command handlers (also gated in CommandRegistry)."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.exceptions import DatabaseError
from bot.handlers.common import matcher_of, repo_of, safe_reply

logger = logging.getLogger(__name__)


async def add_keyword_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if not context.args:
        await safe_reply(update.message, "Укажите ключевое слово: /remove_keyword система не работает")
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


# ---------- База знаний (RAG) ----------
async def add_solution_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ: /add_solution проблема | решение"""
    if not context.args:
        await safe_reply(
            update.message,
            "Формат: /add_solution проблема | решение\n"
            "Пример: /add_solution база зависла | перезагрузите компьютер и проверьте интернет",
        )
        return
    full_text = " ".join(context.args)
    if "|" not in full_text:
        await safe_reply(update.message, "Разделите проблему и решение знаком |")
        return
    problem, solution = full_text.split("|", 1)
    problem, solution = problem.strip(), solution.strip()
    if not problem or not solution:
        await safe_reply(update.message, "И проблема, и решение должны быть непустыми.")
        return
    try:
        repo_of(context).add_solution(problem, solution)
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось сохранить запись.")
        return
    await safe_reply(update.message, "✅ Запись добавлена в базу знаний.")


async def list_kb_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ: /list_kb — показать базу знаний."""
    try:
        rows = repo_of(context).list_all_kb(limit=20)
        total = repo_of(context).count_kb()
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось прочитать базу знаний.")
        return
    if not rows:
        await safe_reply(update.message, "База знаний пуста.")
        return
    response = f"📚 База знаний (всего: {total}):\n\n"
    for r in rows:
        response += f"#{r.id}: {r.problem_text[:60]}\n→ {r.solution_text[:80]}\n\n"
    await safe_reply(update.message, response[:4000])


async def delete_kb_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ: /delete_kb <id>"""
    if not context.args or not context.args[0].isdigit():
        await safe_reply(update.message, "Использование: /delete_kb <id>")
        return
    kb_id = int(context.args[0])
    try:
        removed = repo_of(context).delete_kb(kb_id)
    except DatabaseError:
        await safe_reply(update.message, "❌ Не удалось удалить запись.")
        return
    if not removed:
        await safe_reply(update.message, f"Запись #{kb_id} не найдена.")
        return
    await safe_reply(update.message, f"✅ Запись #{kb_id} удалена.")
