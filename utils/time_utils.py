"""Time / session helpers (UTC)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def utc_hour() -> int:
    return now_utc().hour


def in_session(sessions: dict[str, dict[str, Any]]) -> str | None:
    """Return the active session name (london / new_york / asia) or None.

    Sessions are inclusive of start hour, exclusive of end hour.
    """
    h = utc_hour()
    for name, cfg in sessions.items():
        if not cfg.get("enabled", True):
            continue
        start = int(cfg.get("start", 0))
        end = int(cfg.get("end", 24))
        if start < end:
            if start <= h < end:
                return name
        else:  # wrap-around (e.g., asia 22 -> 6)
            if h >= start or h < end:
                return name
    return None


def is_weekend() -> bool:
    return now_utc().weekday() >= 5  # Sat=5, Sun=6


def fmt_ts(ts: float, fmt: str = "%Y-%m-%d %H:%M") -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(fmt)
