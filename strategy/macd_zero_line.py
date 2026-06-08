"""MACD Zero-Line Scalper.

Trades when MACD crosses the zero line on M1/M5 timeframes.  Often
combined with ATR to size stop-losses dynamically.

Key features:
  - MACD(12, 26, 9) standard settings
  - Zero-line crossover as primary signal
  - ATR-based dynamic stop-loss
  - Histogram momentum confirmation
  - Volume filter (optional)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from data.indicators import atr, ema
from strategy import register_strategy
from strategy.luxalgo_smc import Direction, Signal
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class MACDZeroLineConfig:
    fast: int = 12
    slow: int = 26
    signal: int = 9
    atr_period: int = 14
    atr_sl_mult: float = 1.5       # SL = ATR * mult
    atr_tp_mult: float = 2.0       # TP = ATR * mult
    min_confidence: float = 50.0
    min_rr: float = 1.2
    use_volume_filter: bool = False  # volume often missing or unreliable
    use_histogram_filter: bool = True
    use_volume_filter: bool = False

    @classmethod
    def from_config(cls, cfg: dict) -> MACDZeroLineConfig:
        s = cfg.get("macd_zero_line", {})
        return cls(
            fast=int(s.get("fast", 12)),
            slow=int(s.get("slow", 26)),
            signal=int(s.get("signal", 9)),
            atr_period=int(s.get("atr_period", 14)),
            atr_sl_mult=float(s.get("atr_sl_mult", 1.5)),
            atr_tp_mult=float(s.get("atr_tp_mult", 2.0)),
            min_confidence=float(s.get("min_confidence", 50.0)),
            min_rr=float(s.get("min_rr", 1.0)),
            use_histogram_filter=bool(s.get("use_histogram_filter", True)),
            use_volume_filter=bool(s.get("use_volume_filter", False)),
        )


def _macd(close: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute MACD line, signal line, and histogram."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


@register_strategy(
    "macd_zero_line",
    label="MACD Zero-Line Scalper",
    description="Trades MACD zero-line crossovers on M1/M5. ATR-based dynamic SL/TP.",
    modes=["scalp"],
    icon="macd",
)
class MACDZeroLineScalper:
    """MACD zero-line crossover scalper."""

    def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.cfg = MACDZeroLineConfig.from_config(base_cfg)
        self.mode = mode

    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < self.cfg.slow + self.cfg.signal + 10:
            return self._neutral("insufficient data")

        close = df_ltf["close"]
        macd_line, signal_line, histogram = _macd(close, self.cfg.fast, self.cfg.slow, self.cfg.signal)
        atr_val = atr(df_ltf, self.cfg.atr_period)

        last_macd = float(macd_line.iloc[-1])
        prev_macd = float(macd_line.iloc[-2])
        last_sig = float(signal_line.iloc[-1])
        last_hist = float(histogram.iloc[-1])
        prev_hist = float(histogram.iloc[-2]) if not np.isnan(histogram.iloc[-2]) else 0
        last_atr = float(atr_val.iloc[-1]) if not np.isnan(atr_val.iloc[-1]) else 1.0
        last_close = float(close.iloc[-1])

        # Volume filter
        if self.cfg.use_volume_filter and "volume" in df_ltf.columns:
            vol_avg = float(df_ltf["volume"].rolling(20).mean().iloc[-1])
            last_vol = float(df_ltf["volume"].iloc[-1])
            if last_vol < vol_avg * 0.8:
                return self._neutral("volume below average")

        # Zero-line crossover detection
        crossed_up = prev_macd <= 0 and last_macd > 0
        crossed_down = prev_macd >= 0 and last_macd < 0

        # Position relative to zero line (for fallback signals)
        above_zero = last_macd > 0
        below_zero = last_macd < 0
        histogram_growing = last_hist > prev_hist
        histogram_falling = last_hist < prev_hist

        # Trend persistence: 4+ of last 5 bars above/below zero
        above_count = 0
        below_count = 0
        for i in range(-5, 0):
            if len(macd_line) >= abs(i) + 1:
                if float(macd_line.iloc[i]) > 0:
                    above_count += 1
                elif float(macd_line.iloc[i]) < 0:
                    below_count += 1

        confidence = 55.0
        reasons: list[str] = []
        direction: Direction | None = None
        entry = last_close

        if crossed_up:
            direction = Direction.LONG
            sl = entry - last_atr * self.cfg.atr_sl_mult
            tp = entry + last_atr * self.cfg.atr_tp_mult
            reasons.append(f"MACD crossed above zero ({last_macd:.4f})")
        elif crossed_down:
            direction = Direction.SHORT
            sl = entry + last_atr * self.cfg.atr_sl_mult
            tp = entry - last_atr * self.cfg.atr_tp_mult
            reasons.append(f"MACD crossed below zero ({last_macd:.4f})")
        elif above_zero and above_count >= 4 and histogram_growing:
            # Fallback: MACD above zero + growing histogram
            direction = Direction.LONG
            sl = entry - last_atr * self.cfg.atr_sl_mult
            tp = entry + last_atr * self.cfg.atr_tp_mult
            confidence = 50.0
            reasons.append(f"MACD above zero ({last_macd:.4f}) for {above_count} of last 5 bars")
            reasons.append("histogram growing (bullish momentum)")
        elif below_zero and below_count >= 4 and histogram_falling:
            # Fallback: MACD below zero + falling histogram
            direction = Direction.SHORT
            sl = entry + last_atr * self.cfg.atr_sl_mult
            tp = entry - last_atr * self.cfg.atr_tp_mult
            confidence = 50.0
            reasons.append(f"MACD below zero ({last_macd:.4f}) for {below_count} of last 5 bars")
            reasons.append("histogram falling (bearish momentum)")
        elif above_zero and last_macd > 0.05 and last_hist > 0:
            # Weaker fallback: just above zero
            direction = Direction.LONG
            sl = entry - last_atr * self.cfg.atr_sl_mult
            tp = entry + last_atr * self.cfg.atr_tp_mult
            confidence = 50.0
            reasons.append(f"MACD positive ({last_macd:.4f})")
        elif below_zero and last_macd < -0.05 and last_hist < 0:
            # Weaker fallback: just below zero
            direction = Direction.SHORT
            sl = entry + last_atr * self.cfg.atr_sl_mult
            tp = entry - last_atr * self.cfg.atr_tp_mult
            confidence = 50.0
            reasons.append(f"MACD negative ({last_macd:.4f})")
        else:
            # Final fallback: short-term price momentum
            close_3 = float(close.iloc[-3] if len(close) >= 3 else close.iloc[0])
            change_3 = (last_close - close_3) / close_3 * 100
            if change_3 > 0.005:
                direction = Direction.LONG
                sl = entry - last_atr * self.cfg.atr_sl_mult
                tp = entry + last_atr * self.cfg.atr_tp_mult
                confidence = 45.0
                reasons.append(f"price up {change_3:.2f}% over 3 bars (momentum fallback)")
            elif change_3 < -0.005:
                direction = Direction.SHORT
                sl = entry + last_atr * self.cfg.atr_sl_mult
                tp = entry - last_atr * self.cfg.atr_tp_mult
                confidence = 45.0
                reasons.append(f"price down {abs(change_3):.2f}% over 3 bars (momentum fallback)")
            else:
                return self._neutral(f"no MACD zero-line signal (flat: {change_3:+.3f}%)")

        # Histogram momentum confirmation
        if self.cfg.use_histogram_filter and (crossed_up or crossed_down):
            hist_growing = (last_hist > prev_hist and direction == Direction.LONG) or \
                           (last_hist < prev_hist and direction == Direction.SHORT)
            if not hist_growing:
                return self._neutral("histogram not confirming direction")
            confidence += 5
            reasons.append("histogram confirms direction")

        # Signal line position bonus
        if crossed_up and last_sig > 0:
            confidence += 5
            reasons.append("signal line above zero")
        elif crossed_down and last_sig < 0:
            confidence += 5
            reasons.append("signal line below zero")

        # Magnitude of crossover
        if abs(last_macd) > 0.5:
            confidence += 5
            reasons.append("strong MACD magnitude")
        elif abs(last_macd) > 0.2:
            confidence += 3
            reasons.append("moderate MACD magnitude")

        # HTF bias bonus
        htf_bias = "NEUTRAL"
        if df_htf is not None and len(df_htf) >= 50:
            htf_close = df_htf["close"]
            htf_macd, _, _ = _macd(htf_close, self.cfg.fast, self.cfg.slow, self.cfg.signal)
            if float(htf_macd.iloc[-1]) > 0:
                htf_bias = "BULL"
            else:
                htf_bias = "BEAR"
            if (htf_bias == "BULL" and direction == Direction.LONG) or \
               (htf_bias == "BEAR" and direction == Direction.SHORT):
                confidence += 10
                reasons.append(f"HTF MACD = {htf_bias}")

        reasons.append(f"ATR = {last_atr:.2f}")
        confidence = float(np.clip(confidence, 0, 100))

        if confidence < self.cfg.min_confidence:
            return self._neutral(f"confidence {confidence:.0f}% < {self.cfg.min_confidence}%")

        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = reward / max(risk, 1e-9)
        if rr < self.cfg.min_rr:
            return self._neutral(f"R:R {rr:.2f} < {self.cfg.min_rr}")

        return Signal(
            direction=direction,
            confidence=confidence,
            reasons=reasons,
            htf_bias=htf_bias,
            entry=round(entry, 2),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            rr=round(rr, 2),
            metadata={
                "macd": last_macd,
                "macd_signal": last_sig,
                "macd_histogram": last_hist,
                "atr": last_atr,
                "last_close": last_close,
                "symbol": symbol,
                "strategy": "macd_zero_line",
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
            metadata={"strategy": "macd_zero_line"},
        )

    def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
        macd_line, signal_line, histogram = _macd(df["close"], self.cfg.fast, self.cfg.slow, self.cfg.signal)
        df_out = df.copy()
        df_out["macd"] = macd_line
        df_out["macd_signal"] = signal_line
        df_out["macd_histogram"] = histogram
        return {
            "df": df_out,
            "order_blocks": [],
            "fvgs": [],
            "buy_liquidity": [],
            "sell_liquidity": [],
            "premium_discount": {},
        }
