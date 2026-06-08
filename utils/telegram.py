"""Optional Telegram notifier. Soft-fails if not configured."""
from __future__ import annotations

import os
from typing import Any

import requests

from .logger import get_logger

log = get_logger(__name__)


class Telegram:
    def __init__(self, bot_token: str | None = None, chat_id: str | None = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = (
            os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
            and bool(self.bot_token)
            and bool(self.chat_id)
        )

    def send(self, message: str, **_: Any) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            r = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"},
                timeout=5,
            )
            if not r.ok:
                log.warning("Telegram send failed: %s", r.text)
            return r.ok
        except Exception as e:  # noqa: BLE001
            log.warning("Telegram send error: %s", e)
            return False


_singleton: Telegram | None = None


def notifier() -> Telegram:
    global _singleton
    if _singleton is None:
        _singleton = Telegram()
    return _singleton
