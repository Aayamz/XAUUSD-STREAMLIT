"""Grid Scalper.

Places buy and sell orders at fixed intervals above and below the
current price.  Profits from market oscillation - doesn't predict
direction.  Each grid level has a take-profit.

Key features:
  - Symmetric grid (buy below + sell above current price)
  - Configurable number of levels and spacing
  - TP per grid level (quick scalps)
  - Safety: max exposure cap, total position count limit
  - Range filter (don't grid in strong trends)

Note: This strategy returns a NEUTRAL signal - the actual grid
management is done by the trade execution layer, not by signal
generation.  The Signal here is a "permission" to grid-trade.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from data.indicators import atr
from strategy import register_strategy
from strategy.luxalgo_smc import Direction, Signal
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class GridConfig:
    num_levels: int = 5           # levels above and below
    spacing_atr: float = 0.5      # spacing between levels (multiples of ATR)
    tp_points: int = 20           # TP per grid level
    sl_points: int = 100          # max SL if trend filter fails (safety)
    max_positions: int = 10       # total open positions cap
    min_atr: float = 0.5          # minimum ATR to enable grid
    max_atr: float = 5.0          # maximum ATR (avoid high vol)
    use_range_filter: bool = True
    range_lookback: int = 50
    range_threshold: float = 0.6  # max range / ATR ratio (ranging market)

    @classmethod
    def from_config(cls, cfg: dict) -> GridConfig:
        s = cfg.get("grid_scalper", {})
        return cls(
            num_levels=int(s.get("num_levels", 5)),
            spacing_atr=float(s.get("spacing_atr", 0.5)),
            tp_points=int(s.get("tp_points", 20)),
            sl_points=int(s.get("sl_points", 100)),
            max_positions=int(s.get("max_positions", 10)),
            min_atr=float(s.get("min_atr", 0.5)),
            max_atr=float(s.get("max_atr", 5.0)),
            use_range_filter=bool(s.get("use_range_filter", True)),
            range_lookback=int(s.get("range_lookback", 50)),
            range_threshold=float(s.get("range_threshold", 0.6)),
        )


@register_strategy(
    "grid_scalper",
    label="Grid Scalper",
    description="Places buy/sell orders at fixed intervals. Profits from oscillation, not direction.",
    modes=["scalp"],
    icon="grid",
)
class GridScalper:
    """Grid trading strategy - works best in ranging markets."""

    def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.cfg = GridConfig.from_config(base_cfg)
        self.mode = mode

    def _calculate_grid_levels(self, last_close: float, last_atr: float) -> dict[str, list[float]]:
        """Calculate grid levels around current price."""
        spacing = self.cfg.spacing_atr * last_atr
        buy_levels = []
        sell_levels = []
        for i in range(1, self.cfg.num_levels + 1):
            buy_levels.append(last_close - i * spacing)
            sell_levels.append(last_close + i * spacing)
        return {"buy": buy_levels, "sell": sell_levels}

    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < self.cfg.range_lookback + 10:
            return self._neutral("insufficient data")

        close = df_ltf["close"]
        atr_val = atr(df_ltf, 14)
        last_close = float(close.iloc[-1])
        last_atr = float(atr_val.iloc[-1]) if not np.isnan(atr_val.iloc[-1]) else 1.0

        # ATR bounds
        if last_atr < self.cfg.min_atr:
            return self._neutral(f"ATR {last_atr:.2f} < {self.cfg.min_atr} (too quiet)")
        if last_atr > self.cfg.max_atr:
            return self._neutral(f"ATR {last_atr:.2f} > {self.cfg.max_atr} (too volatile)")

        # Range filter - grid works best in ranging markets
        if self.cfg.use_range_filter and len(df_ltf) >= self.cfg.range_lookback:
            lookback = df_ltf["close"].tail(self.cfg.range_lookback)
            range_size = float(lookback.max() - lookback.min())
            atr_avg = float(atr(df_ltf, 14).tail(self.cfg.range_lookback).mean())
            range_ratio = range_size / max(atr_avg, 1e-9)
            if range_ratio > self.cfg.range_threshold * 20:
                return self._neutral(f"market trending (range/ATR = {range_ratio:.1f})")

        # Calculate grid
        grid = self._calculate_grid_levels(last_close, last_atr)
        spacing = self.cfg.spacing_atr * last_atr

        # Grid is a "market condition allows" signal - return LONG/NEUTRAL/permission
        # The actual buy/sell placement is done by the executor
        # We'll generate a long-biased signal with the grid metadata
        direction = Direction.LONG
        entry = last_close
        sl = entry - self.cfg.sl_points * 0.01
        tp = entry + self.cfg.tp_points * 0.01
        confidence = 50.0

        reasons = [
            f"Grid enabled: {self.cfg.num_levels} levels, {self.cfg.spacing_atr:.1f}x ATR spacing",
            f"Current price {last_close:.2f}",
            f"Buy levels below: {', '.join(f'{x:.2f}' for x in grid['buy'][:3])}...",
            f"Sell levels above: {', '.join(f'{x:.2f}' for x in grid['sell'][:3])}...",
            f"ATR = {last_atr:.2f}",
        ]

        return Signal(
            direction=direction,
            confidence=confidence,
            reasons=reasons,
            htf_bias="NEUTRAL",
            entry=round(entry, 2),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            rr=0.0,
            metadata={
                "grid_buy_levels": grid["buy"],
                "grid_sell_levels": grid["sell"],
                "grid_spacing": spacing,
                "atr": last_atr,
                "last_close": last_close,
                "symbol": symbol,
                "strategy": "grid_scalper",
                "execution_mode": "grid",
            },
            timestamp=time.time(),
        )

    def _neutral(self, reason: str) -> Signal:
        return Signal(
            direction=Direction.NEUTRAL,
            confidence=0.0,
            reasons=[reason],
            htf_bias="NEUTRAL",
            timestamp=time.time(),
            metadata={"strategy": "grid_scalper"},
        )

    def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
        return {
            "df": df,
            "order_blocks": [],
            "fvgs": [],
            "buy_liquidity": [],
            "sell_liquidity": [],
            "premium_discount": {},
        }
