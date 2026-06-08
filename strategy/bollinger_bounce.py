"""Bollinger Band Bounce Scalper.

Buys when price touches the lower band (mean reversion), sells at the
upper band.  Uses RSI to confirm overbought/oversold conditions.  Works
well on ranging/sideways markets.

Key features:
  - 20-period Bollinger Bands (default 2 std dev)
  - RSI(14) filter for extreme conditions
  - Stop at the outer band, target at the middle band
  - Optional ADX filter to avoid trending markets (where BB bounce fails)
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
class BollingerConfig:
    period: int = 20
    std_dev: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    tp_mode: str = "middle"   # "middle" or "points"
    tp_points: int = 30
    sl_points: int = 50
    min_confidence: float = 45.0
    min_rr: float = 1.0
    use_adx_filter: bool = False
    adx_max: float = 25.0  # only trade when ADX < this (ranging market)

    @classmethod
    def from_config(cls, cfg: dict) -> BollingerConfig:
        s = cfg.get("bollinger_bounce", {})
        return cls(
            period=int(s.get("period", 20)),
            std_dev=float(s.get("std_dev", 2.0)),
            rsi_period=int(s.get("rsi_period", 14)),
            rsi_oversold=float(s.get("rsi_oversold", 30.0)),
            rsi_overbought=float(s.get("rsi_overbought", 70.0)),
            tp_mode=s.get("tp_mode", "middle"),
            tp_points=int(s.get("tp_points", 30)),
            sl_points=int(s.get("sl_points", 50)),
            min_confidence=float(s.get("min_confidence", 45.0)),
            min_rr=float(s.get("min_rr", 1.0)),
            use_adx_filter=bool(s.get("use_adx_filter", False)),
            adx_max=float(s.get("adx_max", 25.0)),
        )


def _bollinger_bands(close: pd.Series, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    return upper, sma, lower


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (simplified)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = (high - high.shift(1)).where((high - high.shift(1)) > (low.shift(1) - low), 0)
    minus_dm = (low.shift(1) - low).where((low.shift(1) - low) > (high - high.shift(1)), 0)
    tr = pd.concat([
        (high - low),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx


@register_strategy(
    "bollinger_bounce",
    label="Bollinger Band Bounce",
    description="Mean reversion at BB bands with RSI filter. Best on ranging markets.",
    modes=["scalp"],
    icon="bb-bounce",
)
class BollingerBounceScalper:
    """Bollinger Band mean-reversion scalper."""

    def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.cfg = BollingerConfig.from_config(base_cfg)
        self.mode = mode

    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < self.cfg.period + 10:
            return self._neutral("insufficient data")

        close = df_ltf["close"]
        upper, middle, lower = _bollinger_bands(close, self.cfg.period, self.cfg.std_dev)
        rsi_val = rsi(close, self.cfg.rsi_period)
        atr_val = atr(df_ltf, 14)

        last_close = float(close.iloc[-1])
        last_upper = float(upper.iloc[-1])
        last_middle = float(middle.iloc[-1])
        last_lower = float(lower.iloc[-1])
        prev_close = float(close.iloc[-2])
        prev_lower = float(lower.iloc[-2])
        prev_upper = float(upper.iloc[-2])
        last_rsi = float(rsi_val.iloc[-1])
        last_atr = float(atr_val.iloc[-1]) if not np.isnan(atr_val.iloc[-1]) else 1.0

        # ADX filter (optional) - only trade in ranging markets
        if self.cfg.use_adx_filter:
            adx = _adx(df_ltf, 14)
            last_adx = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 0
            if last_adx > self.cfg.adx_max:
                return self._neutral(f"ADX {last_adx:.0f} > {self.cfg.adx_max} (trending)")

        # Bounce detection (touching band) + proximity detection
        touched_lower = prev_close <= prev_lower and last_close > prev_lower
        touched_upper = prev_close >= prev_upper and last_close < prev_upper
        near_lower = last_close <= last_lower * 1.001  # within 0.1% of lower band
        near_upper = last_close >= last_upper * 0.999  # within 0.1% of upper band

        # Position relative to bands (for fallback signal)
        band_position = (last_close - last_lower) / max(last_upper - last_lower, 1e-9)
        in_lower_half = band_position < 0.4
        in_upper_half = band_position > 0.6

        confidence = 50.0
        reasons: list[str] = []

        if touched_lower or near_lower:
            direction = Direction.LONG
            entry = last_close
            sl = entry - self.cfg.sl_points * 0.01
            if self.cfg.tp_mode == "middle":
                tp = last_middle
            else:
                tp = entry + self.cfg.tp_points * 0.01
            reasons.append(f"price at/near lower BB ({last_lower:.2f})")
            if touched_lower:
                confidence += 10
                reasons.append("BB bounce confirmed (close back above lower band)")
            if last_rsi < self.cfg.rsi_oversold:
                confidence += 10
                reasons.append(f"RSI oversold ({last_rsi:.0f})")
            elif last_rsi < 45:
                confidence += 5
                reasons.append(f"RSI low ({last_rsi:.0f})")
        elif touched_upper or near_upper:
            direction = Direction.SHORT
            entry = last_close
            sl = entry + self.cfg.sl_points * 0.01
            if self.cfg.tp_mode == "middle":
                tp = last_middle
            else:
                tp = entry - self.cfg.tp_points * 0.01
            reasons.append(f"price at/near upper BB ({last_upper:.2f})")
            if touched_upper:
                confidence += 10
                reasons.append("BB bounce confirmed (close back below upper band)")
            if last_rsi > self.cfg.rsi_overbought:
                confidence += 10
                reasons.append(f"RSI overbought ({last_rsi:.0f})")
            elif last_rsi > 55:
                confidence += 5
                reasons.append(f"RSI high ({last_rsi:.0f})")
        elif in_lower_half and last_rsi < 50:
            # Fallback: price in lower half of BB + RSI not overbought
            direction = Direction.LONG
            entry = last_close
            sl = entry - self.cfg.sl_points * 0.01
            if self.cfg.tp_mode == "middle":
                tp = last_middle
            else:
                tp = entry + self.cfg.tp_points * 0.01
            reasons.append(f"price in lower BB region ({band_position:.0%})")
            confidence = 50.0
            if last_rsi < 40:
                confidence += 5
                reasons.append(f"RSI supportive ({last_rsi:.0f})")
        elif in_upper_half and last_rsi > 50:
            # Fallback: price in upper half of BB + RSI not oversold
            direction = Direction.SHORT
            entry = last_close
            sl = entry + self.cfg.sl_points * 0.01
            if self.cfg.tp_mode == "middle":
                tp = last_middle
            else:
                tp = entry - self.cfg.tp_points * 0.01
            reasons.append(f"price in upper BB region ({band_position:.0%})")
            confidence = 50.0
            if last_rsi > 60:
                confidence += 5
                reasons.append(f"RSI supportive ({last_rsi:.0f})")
        else:
            if near_lower or near_upper:
                return self._neutral("at BB band but RSI not confirming")
            # Fallback: short-term price momentum
            close_3 = float(close.iloc[-3] if len(close) >= 3 else close.iloc[0])
            change_3 = (last_close - close_3) / close_3 * 100
            if change_3 > 0.005:
                direction = Direction.LONG
                entry = last_close
                sl = entry - self.cfg.sl_points * 0.01
                if self.cfg.tp_mode == "middle":
                    tp = last_middle
                else:
                    tp = entry + self.cfg.tp_points * 0.01
                confidence = 45.0
                reasons.append(f"price up {change_3:.2f}% over 3 bars (momentum)")
                if last_rsi < 50:
                    confidence += 5
            elif change_3 < -0.005:
                direction = Direction.SHORT
                entry = last_close
                sl = entry + self.cfg.sl_points * 0.01
                if self.cfg.tp_mode == "middle":
                    tp = last_middle
                else:
                    tp = entry - self.cfg.tp_points * 0.01
                confidence = 45.0
                reasons.append(f"price down {abs(change_3):.2f}% over 3 bars (momentum)")
                if last_rsi > 50:
                    confidence += 5
            else:
                return self._neutral(f"price in middle of BB range (flat: {change_3:+.2f}%)")

        reasons.append(f"BB middle = {last_middle:.2f}")
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
                "bb_upper": last_upper,
                "bb_middle": last_middle,
                "bb_lower": last_lower,
                "rsi": last_rsi,
                "atr": last_atr,
                "last_close": last_close,
                "symbol": symbol,
                "strategy": "bollinger_bounce",
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
            metadata={"strategy": "bollinger_bounce"},
        )

    def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
        close = df["close"]
        upper, middle, lower = _bollinger_bands(close, self.cfg.period, self.cfg.std_dev)
        df_out = df.copy()
        df_out["bb_upper"] = upper
        df_out["bb_middle"] = middle
        df_out["bb_lower"] = lower
        return {
            "df": df_out,
            "order_blocks": [],
            "fvgs": [],
            "buy_liquidity": [],
            "sell_liquidity": [],
            "premium_discount": {},
        }
