"""Active trade management: trailing stop, breakeven move, partial TP."""
from __future__ import annotations

import time
from dataclasses import dataclass

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
    note: str = ""


class TradeManager:
    """Maintains trailing stops, moves to BE, and applies partial TPs.

    This class is stateless w.r.t. the broker — the caller is responsible for
    passing in current position data and applying the returned actions.
    """

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or get_config().get("risk", {})
        self._partial_taken: set[int] = set()  # ticket -> partial already taken

    def manage(
        self,
        position: dict,
        df_ltf: pd.DataFrame,
        current_price: float,
    ) -> ManageAction:
        act = ManageAction()
        if df_ltf is None or len(df_ltf) < 20:
            return act

        a = atr(df_ltf, 14).iloc[-1] or 1.0
        side = position["type"]
        entry = position["price_open"]
        sl = position.get("sl") or 0.0
        tp = position.get("tp") or 0.0
        ticket = position["ticket"]

        # ---- Partial take-profit --------------------------------------------
        if (
            self.cfg.get("use_partial_take_profit", True)
            and ticket not in self._partial_taken
            and sl > 0  # Only if SL is set (avoid division by zero issues)
        ):
            target_rr = float(self.cfg.get("partial_tp_rr", 1.0))
            if side == "BUY":
                risk = entry - sl
                if risk <= 0:  # Invalid risk, skip partial TP
                    return act
                partial_price = entry + risk * target_rr
                if current_price >= partial_price:
                    self._partial_taken.add(ticket)
                    act.partial_closed = True
                    act.note = f"partial TP at {partial_price:.2f}"
            else:  # SELL
                risk = sl - entry
                if risk <= 0:  # Invalid risk, skip partial TP
                    return act
                partial_price = entry - risk * target_rr
                if current_price <= partial_price:
                    self._partial_taken.add(ticket)
                    act.partial_closed = True
                    act.note = f"partial TP at {partial_price:.2f}"

        # ---- Breakeven move --------------------------------------------------
        be_after_rr = self.cfg.get("break_even_after_rr", 0)
        if be_after_rr > 0 and sl > 0:  # Only if SL is set
            target_rr = float(be_after_rr)
            if side == "BUY":
                risk = entry - sl
                if risk <= 0:  # Invalid risk, skip BE
                    return act
                be_trigger = entry + risk * target_rr
                if current_price >= be_trigger and sl < entry:
                    act.modified = True
                    act.new_sl = entry
                    sl = entry
            else:
                risk = sl - entry
                if risk <= 0:  # Invalid risk, skip BE
                    return act
                be_trigger = entry - risk * target_rr
                if current_price <= be_trigger and (sl == 0 or sl > entry):
                    act.modified = True
                    act.new_sl = entry
                    sl = entry

        # ---- Trailing stop ---------------------------------------------------
        if self.cfg.get("use_trailing_stop", True):
            trail_mult = float(self.cfg.get("trailing_stop_atr_mult", 1.5))
            if side == "BUY":
                new_sl = current_price - trail_mult * a
                # Only trail if it's profitable and we're not moving SL against the trade
                if new_sl > sl and new_sl > entry:  # never move below entry
                    act.modified = True
                    act.new_sl = new_sl
            else:
                new_sl = current_price + trail_mult * a
                # Only trail if it's profitable and we're not moving SL against the trade
                if (sl == 0 or new_sl < sl) and new_sl < entry:
                    act.modified = True
                    act.new_sl = new_sl

        return act

    def forget(self, ticket: int) -> None:
        self._partial_taken.discard(ticket)
