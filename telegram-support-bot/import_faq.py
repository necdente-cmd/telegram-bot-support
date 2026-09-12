"""Массовая загрузка записей в базу знаний (прямой SQL).

Использование:
    py import_faq.py faq.txt

Формат файла (по одной записи на строку):
    вопрос | ответ
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

from bot.config import get_settings
from bot.db.engine import init_engine, create_all_tables, ensure_columns, session_scope
from bot.db.models import KnowledgeBase
from bot.db.repository import SupportRepository


def parse_faq(path: Path) -> list[tuple[str, str]]:
    """Парсит файл формата «вопрос | ответ»."""
    entries: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                continue
            problem, solution = line.split("|", 1)
            problem, solution = problem.strip(), solution.strip()
            if not problem or not solution:
                continue
            entries.append((problem, solution))
    return entries


def count_existing() -> int:
    """Считает текущее количество записей в базе."""
    try:
        with session_scope() as session:
            return session.query(KnowledgeBase).count()
    except Exception:
        return 0


def get_existing_questions() -> set[str]:
    """Возвращает множество существующих вопросов (для защиты от дублей)."""
    try:
        with session_scope() as session:
            rows = session.query(KnowledgeBase.problem_text).all()
            return {row[0].strip().lower()[:100] for row in rows if row[0]}
    except Exception:
        return set()


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: py import_faq.py <файл.txt>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ Файл не найден: {path}")
        sys.exit(1)

    entries = parse_faq(path)
    if not entries:
        print("❌ Не найдено ни одной записи")
        sys.exit(1)

    print(f"📚 Найдено записей в файле: {len(entries)}\n")

    settings = get_settings()
    init_engine(settings)

    # Создаём таблицы, если их нет (важно для локальной пустой базы)
    try:
        create_all_tables()
        ensure_columns()
        print("✅ Таблицы в базе готовы\n")
    except Exception as exc:
        print(f"⚠️ Ошибка при создании таблиц: {exc}\n")

    repo = SupportRepository()

    # Сколько уже есть в базе
    current_count = count_existing()
    existing_questions = get_existing_questions()
    print(f"🔍 Записей уже в базе: {current_count}\n")

    added = 0
    skipped = 0
    for problem, solution in entries:
        key = problem.strip().lower()[:100]
        if key in existing_questions:
            skipped += 1
            continue
        try:
            repo.add_solution(problem, solution)
            existing_questions.add(key)
            added += 1
            print(f"  ✅ {problem[:70]}")
        except Exception as exc:
            print(f"  ❌ Ошибка при '{problem[:40]}...': {exc}")

    final_count = count_existing()

    print(f"\n🎉 Загружено: {added}")
    if skipped:
        print(f"⏭️  Пропущено (дубли): {skipped}")
    print(f"📊 Всего в базе: {final_count}")


if __name__ == "__main__":
    main()