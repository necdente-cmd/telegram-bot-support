"""Конвертер Markdown → HTML для Telegram.

Telegram поддерживает ограниченный HTML:
- <b>жирный</b>
- <i>курсив</i>
- <code>моно</code>
- <pre>блок</pre>
- <a href="...">ссылка</a>
- <s>зачёркнутый</s>

Этот модуль конвертирует стандартный Markdown от ИИ в безопасный HTML.
"""

from __future__ import annotations

import html
import re


def escape_html(text: str) -> str:
    """Экранирует символы, опасные для Telegram HTML."""
    # Заменяем & первым, потом < и >
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_telegram_html(text: str) -> str:
    """Конвертирует Markdown от ИИ в HTML для Telegram.

    Поддерживает:
    - **bold** → <b>bold</b>
    - *italic* → <i>italic</i>
    - `code` → <code>code</code>
    - ```code block``` → <pre>code block</pre>
    - # Заголовок → <b>Заголовок</b>
    - - пункт / * пункт → • пункт
    - 1. пункт → 1. пункт (как есть)
    - [text](url) → <a href="url">text</a>
    """
    if not text:
        return ""

    # 1. Экранируем HTML-символы
    text = escape_html(text)

    # 2. Блоки кода ``` ... ```
    text = re.sub(
        r"```(?:\w+)?\n?(.*?)```",
        lambda m: f"<pre>{m.group(1).strip()}</pre>",
        text,
        flags=re.DOTALL,
    )

    # 3. Inline код `text`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # 4. Жирный **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    # 5. Жирный __text__
    text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)

    # 6. Курсив *text* (только если не внутри слова)
    text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"<i>\1</i>", text)

    # 7. Курсив _text_
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", text)

    # 8. Ссылки [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )

    # 9. Заголовки # ## ### → <b>текст</b>
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 10. Маркированные списки - или * → •
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.MULTILINE)

    # 11. Схлопываем 3+ пустых строк
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_html_message(html_text: str, max_len: int = 4000) -> list[str]:
    """Разбивает длинный HTML на части, не разрывая теги.

    Простая реализация: разделяет по \n\n на блоки и собирает, пока
    не превысит лимит.
    """
    if len(html_text) <= max_len:
        return [html_text]

    parts: list[str] = []
    current = ""
    for block in html_text.split("\n\n"):
        candidate = (current + "\n\n" + block).strip() if current else block
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                parts.append(current)
            # Если один блок > max_len — режем жёстко
            if len(block) > max_len:
                for i in range(0, len(block), max_len):
                    parts.append(block[i:i + max_len])
                current = ""
            else:
                current = block
    if current:
        parts.append(current)
    return parts
