"""Мини HTTP-сервер для healthcheck Railway.

Railway периодически пингует контейнер по HTTP. Бот использует long polling
и не слушает порты, поэтому Railway может считать его «мертвым» и
перезапускать. Этот сервер отвечает 200 OK на любой GET-запрос и убеждает
Railway, что контейнер жив.
"""

from __future__ import annotations

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    """Отвечает 200 OK на все GET-запросы."""

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_HEAD(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002
        # Отключаем стандартный спам BaseHTTPRequestHandler в логах.
        pass


def start_health_server() -> None:
    """Запускает HTTP-сервер на порту PORT (Railway задаёт его сам).

    Порт берётся из переменной окружения PORT. Если её нет — используется 8080.
    Сервер работает в фоновом daemon-потоке и не блокирует основной цикл бота.
    """
    port = int(os.environ.get("PORT", "8080"))

    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    except OSError as exc:
        logger.error("Не удалось занять порт %s: %s", port, exc)
        return

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Healthcheck-сервер запущен на порту %s", port)
