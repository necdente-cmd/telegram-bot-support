"""Logging setup with console output and rotating file handlers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bot.config import Settings

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(settings: Settings) -> logging.Logger:
    """Configure the root logger: stdout plus a rotating log file.

    Levels are controlled by ``LOG_LEVEL``. File rotation uses
    ``LOG_MAX_BYTES`` and ``LOG_BACKUP_COUNT``.
    """
    level = getattr(logging, settings.log_level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Drop handlers from a previous configure call (useful in tests / reload).
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    log_path: Path = settings.log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Keep noisy HTTP libraries quieter unless we are debugging.
    if level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("telegram.ext").setLevel(logging.INFO)

    logger = logging.getLogger("bot")
    logger.debug("Logging configured (level=%s, file=%s)", settings.log_level, log_path)
    return logger
