"""Массовая загрузка записей в базу знаний.

Использование:
    python import_faq.py faq.txt

Формат файла faq.txt (по одной записи на строку):
    проблема | решение
    база катып жатат | перезагрузите компьютер и проверьте интернет
    ошибка печати | проверьте, установлен ли Adobe Reader

Пустые строки и строки, начинающиеся с #, игнорируются.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Загружаем .env (если есть)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from bot.config import get_settings
from bot.db.engine import init_engine
from bot.db.repository import SupportRepository


def parse_faq(path: Path) -> list[tuple[str, str]]:
    """Парсит файл формата «проблема | решение»."""
    entries: list[tuple[str, str]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                print(f"⚠️  Строка {line_no}: пропущена (нет |): {line[:60]}")
                continue
            problem, solution = line.split("|", 1)
            problem, solution = problem.strip(), solution.strip()
            if not problem or not solution:
                print(f"⚠️  Строка {line_no}: пустая проблема или решение")
                continue
            entries.append((problem, solution))
    return entries


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python import_faq.py <файл.txt>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ Файл не найден: {path}")
        sys.exit(1)

    entries = parse_faq(path)
    if not entries:
        print("❌ Не найдено ни одной записи формата «проблема | решение»")
        sys.exit(1)

    print(f"📚 Найдено записей: {len(entries)}")

    settings = get_settings()
    init_engine(settings)
    repo = SupportRepository()

    added = 0
    for problem, solution in entries:
        try:
            repo.add_solution(problem, solution)
            added += 1
            print(f"  ✅ {problem[:60]}")
        except Exception as exc:
            print(f"  ❌ Ошибка при '{problem[:40]}...': {exc}")

    print(f"\n🎉 Загружено: {added}/{len(entries)}")
    print(f"📊 Всего в базе: {repo.count_kb()}")


if __name__ == "__main__":
    main()
