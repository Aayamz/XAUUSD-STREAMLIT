"""Centralised logging setup — JSON lines for trade journal + human readable for console."""
from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_FILE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"
_CONSOLE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"


def _build_logger(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level.upper())
    logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt="%H:%M:%S"))
    logger.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "bot.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FILE_FMT))
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """Module-level logger factory."""
    if level is None:
        try:
            from .config import get_config

            level = get_config().get("app.log_level", "INFO")
        except Exception:
            level = "INFO"
    return _build_logger(name, level)


def log_trade(event: dict[str, Any]) -> None:
    """Append a structured trade event to trades.jsonl for the journal/performance page."""
    import json
    import time

    event = {"ts": time.time(), **event}
    path = LOG_DIR / "trades.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")
