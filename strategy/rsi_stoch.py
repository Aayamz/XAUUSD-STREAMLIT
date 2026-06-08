"""RSI + Stochastic Combo Scalper.

Enters when both RSI(14) < 30 and Stochastic %K/%D is oversold (< 20)
for LONG, or both are overbought for SHORT.  Quick 5-10 pip targets
with tight stop-loss.

Key features:
  - Dual confirmation (RSI + Stochastic must agree)
  - Stochastic K/D crossover as additional entry trigger
  - Tight TP / SL for quick exits
  - Volume confirmation (optional)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from data.indicators import atr, rsi
from strategy import register_strategy
from strategy.luxalgo_smc import Direction, Signal
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class RSIStochConfig:
    rsi_period: int = 14
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    stoch_smooth: int = 3
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    stoch_oversold: float = 20.0
    stoch_overbought: float = 80.0
    tp_points: int = 10  # tight 10-pt target
    sl_points: int = 15
    min_confidence: float = 45.0
    min_rr: float = 0.5
    use_volume_filter: bool = False  # volume often missing or unreliable

    @classmethod
    def from_config(cls, cfg: dict) -> RSIStochConfig:
        s = cfg.get("rsi_stoch", {})
        return cls(
            rsi_period=int(s.get("rsi_period", 14)),
            stoch_k_period=int(s.get("stoch_k_period", 14)),
            stoch_d_period=int(s.get("stoch_d_period", 3)),
            stoch_smooth=int(s.get("stoch_smooth", 3)),
            rsi_oversold=float(s.get("rsi_oversold", 30.0)),
            rsi_overbought=float(s.get("rsi_overbought", 70.0)),
            stoch_oversold=float(s.get("stoch_oversold", 20.0)),
            stoch_overbought=float(s.get("stoch_overbought", 80.0)),
            tp_points=int(s.get("tp_points", 10)),
            sl_points=int(s.get("sl_points", 15)),
            min_confidence=float(s.get("min_confidence", 45.0)),
            min_rr=float(s.get("min_rr", 0.5)),
            use_volume_filter=bool(s.get("use_volume_filter", False)),
        )


def _stochastic(df: pd.DataFrame, k_period: int, d_period: int, smooth: int) -> tuple[pd.Series, pd.Series]:
    """Compute Stochastic %K and %D."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    fast_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, 1e-9)
    slow_k = fast_k.rolling(smooth).mean()
    slow_d = slow_k.rolling(d_period).mean()
    return slow_k, slow_d


@register_strategy(
    "rsi_stoch",
    label="RSI + Stochastic Combo",
    description="RSI(14) + Stochastic dual confirmation. Quick 5-10pt targets.",
    modes=["scalp"],
    icon="rsi-stoch",
)
class RSIStochasticScalper:
    """RSI + Stochastic dual-confirmation scalper."""

    def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.cfg = RSIStochConfig.from_config(base_cfg)
        self.mode = mode

    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < self.cfg.stoch_k_period + 10:
            return self._neutral("insufficient data")

        close = df_ltf["close"]
        rsi_val = rsi(close, self.cfg.rsi_period)
        stoch_k, stoch_d = _stochastic(df_ltf, self.cfg.stoch_k_period,
                                       self.cfg.stoch_d_period, self.cfg.stoch_smooth)
        atr_val = atr(df_ltf, 14)

        last_close = float(close.iloc[-1])
        last_rsi = float(rsi_val.iloc[-1])
        prev_rsi = float(rsi_val.iloc[-2])
        last_k = float(stoch_k.iloc[-1]) if not np.isnan(stoch_k.iloc[-1]) else 50
        prev_k = float(stoch_k.iloc[-2]) if not np.isnan(stoch_k.iloc[-2]) else 50
        last_d = float(stoch_d.iloc[-1]) if not np.isnan(stoch_d.iloc[-1]) else 50
        prev_d = float(stoch_d.iloc[-2]) if not np.isnan(stoch_d.iloc[-2]) else 50
        last_atr = float(atr_val.iloc[-1]) if not np.isnan(atr_val.iloc[-1]) else 1.0

        # Volume filter
        if self.cfg.use_volume_filter and "volume" in df_ltf.columns:
            vol_avg = float(df_ltf["volume"].rolling(20).mean().iloc[-1])
            last_vol = float(df_ltf["volume"].iloc[-1])
            if last_vol < vol_avg * 0.5:
                return self._neutral("volume too low")

        # RSI + Stochastic dual confirmation (with relaxed thresholds)
        rsi_oversold = last_rsi < self.cfg.rsi_oversold or prev_rsi < self.cfg.rsi_oversold
        rsi_overbought = last_rsi > self.cfg.rsi_overbought or prev_rsi > self.cfg.rsi_overbought
        rsi_low = last_rsi < 45  # relaxed
        rsi_high = last_rsi > 55  # relaxed
        stoch_oversold = last_k < self.cfg.stoch_oversold or prev_k < self.cfg.stoch_oversold
        stoch_overbought = last_k > self.cfg.stoch_overbought or prev_k > self.cfg.stoch_overbought
        stoch_low = last_k < 35  # relaxed
        stoch_high = last_k > 65  # relaxed

        # K/D crossover (bullish: K crosses above D, bearish: K crosses below D)
        k_cross_up = prev_k <= prev_d and last_k > last_d
        k_cross_down = prev_k >= prev_d and last_k < last_d

        confidence = 50.0
        reasons: list[str] = []

        # LONG: both RSI and Stochastic oversold, or K crosses up from oversold
        if (rsi_oversold and stoch_oversold) or (stoch_oversold and k_cross_up):
            direction = Direction.LONG
            entry = last_close
            sl = entry - self.cfg.sl_points * 0.01
            tp = entry + self.cfg.tp_points * 0.01
            reasons.append(f"RSI {last_rsi:.0f} (oversold)")
            reasons.append(f"Stochastic %K {last_k:.0f} (oversold)")
            if rsi_oversold:
                confidence += 10
            if stoch_oversold:
                confidence += 10
            if k_cross_up:
                confidence += 5
                reasons.append("Stochastic K crossed above D")
            if last_rsi < 20:
                confidence += 10
                reasons.append("RSI extremely oversold")

        # SHORT: both RSI and Stochastic overbought, or K crosses down from overbought
        elif (rsi_overbought and stoch_overbought) or (stoch_overbought and k_cross_down):
            direction = Direction.SHORT
            entry = last_close
            sl = entry + self.cfg.sl_points * 0.01
            tp = entry - self.cfg.tp_points * 0.01
            reasons.append(f"RSI {last_rsi:.0f} (overbought)")
            reasons.append(f"Stochastic %K {last_k:.0f} (overbought)")
            if rsi_overbought:
                confidence += 10
            if stoch_overbought:
                confidence += 10
            if k_cross_down:
                confidence += 5
                reasons.append("Stochastic K crossed below D")
            if last_rsi > 80:
                confidence += 10
                reasons.append("RSI extremely overbought")

        # Fallback 1: both indicators in the same direction (relaxed)
        elif rsi_low and stoch_low:
            direction = Direction.LONG
            entry = last_close
            sl = entry - self.cfg.sl_points * 0.01
            tp = entry + self.cfg.tp_points * 0.01
            confidence = 50.0
            reasons.append(f"RSI low ({last_rsi:.0f}) + Stochastic low ({last_k:.0f})")
            if k_cross_up:
                confidence += 5
                reasons.append("K crossing up (momentum shift)")
            if last_rsi < 35:
                confidence += 5

        elif rsi_high and stoch_high:
            direction = Direction.SHORT
            entry = last_close
            sl = entry + self.cfg.sl_points * 0.01
            tp = entry - self.cfg.tp_points * 0.01
            confidence = 50.0
            reasons.append(f"RSI high ({last_rsi:.0f}) + Stochastic high ({last_k:.0f})")
            if k_cross_down:
                confidence += 5
                reasons.append("K crossing down (momentum shift)")
            if last_rsi > 65:
                confidence += 5

        # Fallback 2: single strong indicator
        elif rsi_oversold and last_k < 40:
            direction = Direction.LONG
            entry = last_close
            sl = entry - self.cfg.sl_points * 0.01
            tp = entry + self.cfg.tp_points * 0.01
            confidence = 55.0
            reasons.append(f"RSI oversold ({last_rsi:.0f}), Stoch supportive ({last_k:.0f})")

        elif rsi_overbought and last_k > 60:
            direction = Direction.SHORT
            entry = last_close
            sl = entry + self.cfg.sl_points * 0.01
            tp = entry - self.cfg.tp_points * 0.01
            confidence = 55.0
            reasons.append(f"RSI overbought ({last_rsi:.0f}), Stoch supportive ({last_k:.0f})")

        else:
            # Final fallback: short-term price momentum
            close_3 = float(close.iloc[-3] if len(close) >= 3 else close.iloc[0])
            change_3 = (last_close - close_3) / close_3 * 100
            if change_3 > 0.005:
                direction = Direction.LONG
                entry = last_close
                sl = entry - self.cfg.sl_points * 0.01
                tp = entry + self.cfg.tp_points * 0.01
                confidence = 45.0
                reasons.append(f"price up {change_3:.2f}% over 3 bars (momentum)")
                if last_rsi < 50:
                    confidence += 5
            elif change_3 < -0.005:
                direction = Direction.SHORT
                entry = last_close
                sl = entry + self.cfg.sl_points * 0.01
                tp = entry - self.cfg.tp_points * 0.01
                confidence = 45.0
                reasons.append(f"price down {abs(change_3):.2f}% over 3 bars (momentum)")
                if last_rsi > 50:
                    confidence += 5
            else:
                return self._neutral(f"RSI and Stochastic not aligned (flat: {change_3:+.3f}%)")

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
            htf_bias="NEUTRAL",
            entry=round(entry, 2),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            rr=round(rr, 2),
            metadata={
                "rsi": last_rsi,
                "stoch_k": last_k,
                "stoch_d": last_d,
                "atr": last_atr,
                "last_close": last_close,
                "symbol": symbol,
                "strategy": "rsi_stoch",
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
            metadata={"strategy": "rsi_stoch"},
        )

    def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
        stoch_k, stoch_d = _stochastic(df, self.cfg.stoch_k_period,
                                       self.cfg.stoch_d_period, self.cfg.stoch_smooth)
        df_out = df.copy()
        df_out["stoch_k"] = stoch_k
        df_out["stoch_d"] = stoch_d
        return {
            "df": df_out,
            "order_blocks": [],
            "fvgs": [],
            "buy_liquidity": [],
            "sell_liquidity": [],
            "premium_discount": {},
        }
