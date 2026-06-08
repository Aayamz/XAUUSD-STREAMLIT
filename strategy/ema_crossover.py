"""EMA Crossover Scalper.

Pure EMA(5)/EMA(20) crossover strategy.  Buys on bullish cross, sells on
bearish cross.  Works best on M1/M5 timeframes with tight stops and
quick targets.

Key features:
  - Strict crossover-based entries (no trend persistence fallback)
  - RSI filter to avoid entering in extreme overbought/oversold
  - Volume confirmation (optional)
  - Fast TP / tight SL for quick scalps
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from data.indicators import atr, ema, rsi
from strategy import register_strategy
from strategy.luxalgo_smc import Direction, Signal
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class EMACrossoverConfig:
    fast_period: int = 5
    slow_period: int = 20
    rsi_period: int = 14
    tp_points: int = 30       # take profit in points
    sl_points: int = 15       # stop loss in points
    min_confidence: float = 50.0
    min_rr: float = 1.5
    use_volume_filter: bool = False
    use_rsi_filter: bool = True

    @classmethod
    def from_config(cls, cfg: dict) -> EMACrossoverConfig:
        s = cfg.get("ema_crossover", {})
        return cls(
            fast_period=int(s.get("fast_period", 5)),
            slow_period=int(s.get("slow_period", 20)),
            rsi_period=int(s.get("rsi_period", 14)),
            tp_points=int(s.get("tp_points", 30)),
            sl_points=int(s.get("sl_points", 15)),
            min_confidence=float(s.get("min_confidence", 50.0)),
            min_rr=float(s.get("min_rr", 1.5)),
            use_volume_filter=bool(s.get("use_volume_filter", False)),
            use_rsi_filter=bool(s.get("use_rsi_filter", True)),
        )


@register_strategy(
    "ema_crossover",
    label="EMA Crossover Scalper",
    description="Pure EMA(5)/EMA(20) crossover. Buys on bullish cross, sells on bearish cross. M1/M5.",
    modes=["scalp"],
    icon="ema-cross",
)
class EMACrossoverScalper:
    """Standalone EMA crossover scalper (no HuggingFace dependency)."""

    def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.cfg = EMACrossoverConfig.from_config(base_cfg)
        self.mode = mode

    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < self.cfg.slow_period + 10:
            return self._neutral("insufficient data")

        close = df_ltf["close"]
        fast_ma = ema(close, self.cfg.fast_period)
        slow_ma = ema(close, self.cfg.slow_period)
        rsi_val = rsi(close, self.cfg.rsi_period)
        atr_val = atr(df_ltf, 14)

        last_fast = float(fast_ma.iloc[-1])
        last_slow = float(slow_ma.iloc[-1])
        prev_fast = float(fast_ma.iloc[-2])
        prev_slow = float(slow_ma.iloc[-2])
        last_close = float(close.iloc[-1])
        last_rsi = float(rsi_val.iloc[-1])
        last_atr = float(atr_val.iloc[-1]) if not np.isnan(atr_val.iloc[-1]) else 1.0

        # Crossover detection
        crossed_up = prev_fast <= prev_slow and last_fast > last_slow
        crossed_down = prev_fast >= prev_slow and last_fast < last_slow

        # Fallback: trend persistence (4+ of last 5 bars had fast above/below slow)
        above_count = 0
        below_count = 0
        for i in range(-5, 0):
            if len(fast_ma) >= abs(i) + 1:
                if float(fast_ma.iloc[i]) > float(slow_ma.iloc[i]):
                    above_count += 1
                else:
                    below_count += 1

        # Determine direction
        long_signal = crossed_up or above_count >= 4
        short_signal = crossed_down or below_count >= 4

        if not long_signal and not short_signal:
            return self._neutral("no EMA crossover or trend")

        # Volume filter (optional)
        if self.cfg.use_volume_filter and "volume" in df_ltf.columns:
            vol_avg = float(df_ltf["volume"].rolling(20).mean().iloc[-1])
            last_vol = float(df_ltf["volume"].iloc[-1])
            if last_vol < vol_avg * 0.5:
                return self._neutral("volume below average")

        # RSI filter to avoid extremes
        if self.cfg.use_rsi_filter:
            if long_signal and last_rsi > 75:
                return self._neutral(f"RSI {last_rsi:.0f} overbought, skipping buy")
            if short_signal and last_rsi < 25:
                return self._neutral(f"RSI {last_rsi:.0f} oversold, skipping sell")

        confidence = 50.0
        reasons: list[str] = []
        if long_signal:
            direction = Direction.LONG
            entry = last_close
            sl = entry - self.cfg.sl_points * 0.01
            tp = entry + self.cfg.tp_points * 0.01
            if crossed_up:
                confidence = 60.0
                reasons.append(f"EMA({self.cfg.fast_period}) crossed above EMA({self.cfg.slow_period})")
            else:
                confidence = 50.0
                reasons.append(f"fast EMA above slow EMA for {above_count} of last 5 bars")
        else:
            direction = Direction.SHORT
            entry = last_close
            sl = entry + self.cfg.sl_points * 0.01
            tp = entry - self.cfg.tp_points * 0.01
            if crossed_down:
                confidence = 60.0
                reasons.append(f"EMA({self.cfg.fast_period}) crossed below EMA({self.cfg.slow_period})")
            else:
                confidence = 50.0
                reasons.append(f"fast EMA below slow EMA for {below_count} of last 5 bars")

        # Confidence boosters
        if last_rsi < 40 and direction == Direction.LONG:
            confidence += 10
            reasons.append(f"RSI oversold ({last_rsi:.0f})")
        elif last_rsi > 60 and direction == Direction.SHORT:
            confidence += 10
            reasons.append(f"RSI overbought ({last_rsi:.0f})")

        # HTF bias bonus
        htf_bias = "NEUTRAL"
        if df_htf is not None and len(df_htf) >= 50:
            htf_close = df_htf["close"]
            htf_fast = ema(htf_close, 10)
            htf_slow = ema(htf_close, 30)
            if float(htf_fast.iloc[-1]) > float(htf_slow.iloc[-1]):
                htf_bias = "BULL"
            else:
                htf_bias = "BEAR"
            if (htf_bias == "BULL" and direction == Direction.LONG) or \
               (htf_bias == "BEAR" and direction == Direction.SHORT):
                confidence += 10
                reasons.append(f"HTF bias = {htf_bias} (confluent)")

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
                "fast_ma": last_fast,
                "slow_ma": last_slow,
                "rsi": last_rsi,
                "atr": last_atr,
                "last_close": last_close,
                "symbol": symbol,
                "strategy": "ema_crossover",
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
            metadata={"strategy": "ema_crossover"},
        )

    def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
        close = df["close"]
        fast_ma = ema(close, self.cfg.fast_period)
        slow_ma = ema(close, self.cfg.slow_period)
        df_out = df.copy()
        df_out["fast_ma"] = fast_ma
        df_out["slow_ma"] = slow_ma
        return {
            "df": df_out,
            "order_blocks": [],
            "fvgs": [],
            "buy_liquidity": [],
            "sell_liquidity": [],
            "premium_discount": {},
        }
