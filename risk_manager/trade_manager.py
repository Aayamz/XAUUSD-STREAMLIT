"""Active trade management: multiple TPs, trailing stop, breakeven move."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from data.indicators import atr
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)

import pandas as pd


@dataclass
class ManageAction:
    """Outcome of managing an open position."""
    modified: bool = False
    partial_closed: bool = False
    full_closed: bool = False
    new_sl: float | None = None
    new_tp: float | None = None
    partial_close_volume: float | None = None
    note: str = ""


# Default multi-TP levels: list of (rr_target, close_pct)
DEFAULT_TP_LEVELS = [
    {"rr": 1.0, "close_pct": 30},
    {"rr": 2.0, "close_pct": 30},
    {"rr": 3.0, "close_pct": 40},
]


class TradeManager:
    """Multi-TP, trailing stop, breakeven move, and partial closes.

    TP levels are configured via ``risk.tp_levels`` in config.yaml::

        tp_levels:
          - rr: 1.0
            close_pct: 30
          - rr: 2.0
            close_pct: 30
          - rr: 3.0
            close_pct: 40

    Trailing stop activates after ``trailing_start_rr`` (default 1.0R).
    """

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or get_config().get("risk", {})
        self._tp_hit: dict[int, list[int]] = {}  # ticket -> indices of TP levels already hit
        self._sl_moved_to_be: set[int] = set()   # tickets already moved to breakeven

    # ------------------------------------------------------------------
    def _tp_levels(self) -> list[dict]:
        raw = self.cfg.get("tp_levels")
        if raw and isinstance(raw, list) and len(raw) > 0:
            return raw
        return DEFAULT_TP_LEVELS

    def _risk(self, position: dict, atr_val: float = 1.0) -> float:
        """Return the risk distance (entry - SL or SL - entry).

        If the position has no SL or SL is at/above entry (for BUY),
        fall back to 1.5 * ATR so that TP/BE/trailing logic can still operate.
        """
        side = position["type"]
        entry = position["price_open"]
        sl = position.get("sl")

        if sl is None or sl == 0:
            return atr_val * 1.5

        if side == "BUY":
            risk = entry - sl
            return risk if risk > 0 else atr_val * 1.5
        else:
            risk = sl - entry
            return risk if risk > 0 else atr_val * 1.5

    def manage(
        self,
        position: dict,
        df_ltf: pd.DataFrame,
        current_price: float,
    ) -> ManageAction:
        act = ManageAction()
        if df_ltf is None or len(df_ltf) < 20:
            return act

        a = float(atr(df_ltf, 14).iloc[-1]) or 1.0
        side = position["type"]
        entry = position["price_open"]
        sl = position.get("sl") or 0.0
        tp = position.get("tp") or 0.0
        ticket = position["ticket"]
        volume = position.get("volume", 0.0)

        risk = self._risk(position, atr_val=a)
        if risk <= 0:
            return act

        if side == "BUY":
            current_rr = (current_price - entry) / risk
        else:
            current_rr = (entry - current_price) / risk

        log.debug(
            "manage ticket=%s side=%s entry=%.2f sl=%.2f cur=%.2f risk=%.2f rr=%.2f",
            ticket, side, entry, sl, current_price, risk, current_rr,
        )

        # ---- 1. Multi-level take-profit -----------------------------------
        if self.cfg.get("use_partial_take_profit", True) and volume > 0:
            if ticket not in self._tp_hit:
                self._tp_hit[ticket] = []
            tp_levels = self._tp_levels()
            for idx, level in enumerate(tp_levels):
                if idx in self._tp_hit[ticket]:
                    continue
                target_rr = float(level.get("rr", 1.0))
                close_pct = float(level.get("close_pct", 30))
                if current_rr >= target_rr:
                    close_vol = round(volume * close_pct / 100, 2)
                    # Ensure minimum close volume (0.01 lot)
                    close_vol = max(close_vol, 0.01)
                    if close_vol <= 0:
                        continue
                    # Ensure we don't close more than remaining volume
                    already_closed = sum(
                        round(volume * tp_levels[i].get("close_pct", 30) / 100, 2)
                        for i in self._tp_hit[ticket]
                    )
                    close_vol = min(close_vol, round(volume - already_closed, 2))
                    if close_vol <= 0:
                        continue
                    self._tp_hit[ticket].append(idx)
                    act.partial_closed = True
                    act.partial_close_volume = close_vol
                    act.note = f"TP{idx+1} hit at {target_rr:.1f}R — closing {close_pct}% ({close_vol} lots)"
                    log.info("TP%d hit ticket=%s rr=%.1f close=%.2f lots",
                             idx + 1, ticket, target_rr, close_vol)
                    break  # handle one TP level per tick

        # ---- 2. Breakeven move --------------------------------------------
        be_after_rr = float(self.cfg.get("break_even_after_rr", 0))
        if be_after_rr > 0 and sl > 0 and ticket not in self._sl_moved_to_be:
            if side == "BUY" and current_rr >= be_after_rr and sl < entry:
                act.modified = True
                act.new_sl = entry
                self._sl_moved_to_be.add(ticket)
                sl = entry
                log.info("BE move ticket=%s sl -> %.2f", ticket, entry)
            elif side == "SELL" and current_rr >= be_after_rr and sl > entry:
                act.modified = True
                act.new_sl = entry
                self._sl_moved_to_be.add(ticket)
                sl = entry
                log.info("BE move ticket=%s sl -> %.2f", ticket, entry)

        # ---- 3. Trailing stop ---------------------------------------------
        if self.cfg.get("use_trailing_stop", True):
            trail_mult = float(self.cfg.get("trailing_stop_atr_mult", 1.5))
            # Only start trailing after we're at least trailing_start_rr in profit
            trailing_start_rr = float(self.cfg.get("trailing_start_rr", 1.0))
            if current_rr >= trailing_start_rr:
                if side == "BUY":
                    new_sl = current_price - trail_mult * a
                    if new_sl > sl and new_sl > entry:
                        act.modified = True
                        act.new_sl = new_sl
                else:
                    new_sl = current_price + trail_mult * a
                    if (sl == 0 or new_sl < sl) and new_sl < entry:
                        act.modified = True
                        act.new_sl = new_sl

        # ---- 4. Full TP hit (MT5 auto-closes) -----------------------------
        # If price reached the last TP level, MT5 will handle the close.
        # We just clean up our tracking state.
        if tp > 0:
            if side == "BUY" and current_price >= tp:
                self.forget(ticket)
            elif side == "SELL" and current_price <= tp:
                self.forget(ticket)

        return act

    def forget(self, ticket: int) -> None:
        self._tp_hit.pop(ticket, None)
        self._sl_moved_to_be.discard(ticket)
