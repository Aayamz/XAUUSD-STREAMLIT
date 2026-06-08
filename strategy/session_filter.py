"""Session filter (UTC) — wrap of utils.time_utils so it lives in the strategy pkg."""
from __future__ import annotations

from utils.config import get_config
from utils.time_utils import in_session, is_weekend


def active_session() -> str | None:
    cfg = get_config().get("strategy", {}).get("sessions", {})
    return in_session(cfg) if cfg else None


def trading_allowed() -> bool:
    """True if the current moment is inside an enabled session and not weekend, unless session filter is ignored."""
    config = get_config().get("strategy", {})
    if config.get("ignore_session_filter", False):
        # Ignore session and weekend filters
        return True
    if is_weekend():
        return False
    return active_session() is not None
