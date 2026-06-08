"""Hard risk limits and stateful tracking.

Tracks daily P&L, peak equity, drawdown. The ``RiskLimits.check()`` method
returns a ``Decision`` describing whether new trades are allowed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone

from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


class RiskLimits:
    def __init__(self):
        self.cfg = get_config().get("risk", {})
        self._day_key = self._today_key()
        self._daily_pnl: float = 0.0
        self._peak_equity: float = 0.0

    # --- public ---------------------------------------------------------------
    def update(self, equity: float, closed_pnl: float = 0.0) -> None:
        """Call on every tick with current equity and any realised P&L since last call."""
        if self._today_key() != self._day_key:
            self._day_key = self._today_key()
            self._daily_pnl = 0.0
        self._daily_pnl += closed_pnl
        self._peak_equity = max(self._peak_equity, equity)

    def check(self, equity: float, open_positions: int) -> Decision:
        daily_limit = -abs(float(self.cfg.get("daily_loss_limit_pct", 4.0))) / 100.0 * self._peak_equity
        max_dd = -abs(float(self.cfg.get("max_drawdown_pct", 12.0))) / 100.0 * self._peak_equity
        max_pos = int(self.cfg.get("max_concurrent_positions", 1))

        if self._peak_equity == 0:
            self._peak_equity = equity
        dd = equity - self._peak_equity

        if open_positions >= max_pos:
            return Decision(False, f"max concurrent positions reached ({open_positions}/{max_pos})")
        if self._daily_pnl <= daily_limit and daily_limit != 0:
            return Decision(False, f"daily loss limit hit ({self._daily_pnl:.2f} <= {daily_limit:.2f})")
        if dd <= max_dd and max_dd != 0:
            return Decision(False, f"max drawdown hit ({dd:.2f} <= {max_dd:.2f})")
        return Decision(True, "ok")

    # --- helpers --------------------------------------------------------------
    @staticmethod
    def _today_key() -> str:
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def drawdown_pct(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return ((self._peak_equity - (self._peak_equity + (self._daily_pnl if self._daily_pnl < 0 else 0))) / self._peak_equity) * 100
