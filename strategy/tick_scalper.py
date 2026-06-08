"""Tick Scalper / News Scalper.

Fires trades based on sudden volume spikes (news events, large orders).
Detects anomalies in volume compared to recent average, then enters
in the direction of price momentum.

Key features:
  - Volume spike detection (Z-score above rolling mean)
  - Price momentum confirmation
  - Tight TP / SL (very fast execution)
  - Cooldown period to avoid over-trading
  - Best during high-impact news releases

Requires:
  - Volume data in OHLCV (which MT5 provides)
  - Low-latency execution (close to broker)
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
class TickScalperConfig:
    volume_lookback: int = 20        # bars for average volume
    spike_zscore: float = 2.0        # volume Z-score threshold
    min_spike_volume: float = 1.5    # minimum volume / avg ratio
    momentum_bars: int = 3           # bars to measure momentum
    momentum_threshold: float = 0.5  # minimum price change in ATR units
    tp_points: int = 15              # quick TP
    sl_points: int = 20              # tight SL
    cooldown_bars: int = 5           # bars to wait between signals
    min_confidence: float = 55.0
    min_rr: float = 0.5

    @classmethod
    def from_config(cls, cfg: dict) -> TickScalperConfig:
        s = cfg.get("tick_scalper", {})
        return cls(
            volume_lookback=int(s.get("volume_lookback", 20)),
            spike_zscore=float(s.get("spike_zscore", 2.0)),
            min_spike_volume=float(s.get("min_spike_volume", 1.5)),
            momentum_bars=int(s.get("momentum_bars", 3)),
            momentum_threshold=float(s.get("momentum_threshold", 0.5)),
            tp_points=int(s.get("tp_points", 15)),
            sl_points=int(s.get("sl_points", 20)),
            cooldown_bars=int(s.get("cooldown_bars", 5)),
            min_confidence=float(s.get("min_confidence", 55.0)),
            min_rr=float(s.get("min_rr", 0.5)),
        )


@register_strategy(
    "tick_scalper",
    label="Tick / News Scalper",
    description="Fires on volume spikes (news events). Tight TP/SL, fast execution required.",
    modes=["scalp"],
    icon="tick",
)
class TickScalper:
    """Volume-spike news scalper."""

    def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.cfg = TickScalperConfig.from_config(base_cfg)
        self.mode = mode
        self._last_signal_bar = -1000  # track last signal bar index

    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < self.cfg.volume_lookback + 10:
            return self._neutral("insufficient data")
        if "volume" not in df_ltf.columns:
            return self._neutral("no volume data")

        volume = df_ltf["volume"]
        close = df_ltf["close"]
        atr_val = atr(df_ltf, 14)

        # Volume statistics
        vol_avg = volume.rolling(self.cfg.volume_lookback).mean()
        vol_std = volume.rolling(self.cfg.volume_lookback).std()
        last_vol = float(volume.iloc[-1])
        last_vol_avg = float(vol_avg.iloc[-1])
        last_vol_std = float(vol_std.iloc[-1]) if not np.isnan(vol_std.iloc[-1]) else 0
        last_close = float(close.iloc[-1])

        vol_zscore = (last_vol - last_vol_avg) / max(last_vol_std, 1e-9)
        vol_ratio = last_vol / max(last_vol_avg, 1e-9)

        # Spike detection (relaxed thresholds)
        is_spike = vol_zscore >= self.cfg.spike_zscore and vol_ratio >= self.cfg.min_spike_volume
        # Mild spike fallback (volume above 1.05x average with positive z)
        is_mild = vol_ratio >= 1.05 and vol_zscore >= 0.0

        # Cooldown check
        current_bar = len(df_ltf) - 1
        if current_bar - self._last_signal_bar < self.cfg.cooldown_bars:
            return self._neutral("cooldown period active")

        # Momentum (price change over last N bars)
        momentum = float(close.iloc[-1] - close.iloc[-self.cfg.momentum_bars - 1])
        last_atr = float(atr_val.iloc[-1]) if not np.isnan(atr_val.iloc[-1]) else 1.0
        momentum_atr = momentum / max(last_atr, 1e-9)

        # Final fallback: price momentum even without volume spike
        if not is_spike and not is_mild:
            close_3 = float(close.iloc[-3] if len(close) >= 3 else close.iloc[0])
            change_3 = (last_close - close_3) / last_close * 100
            if abs(change_3) < 0.005:
                return self._neutral(f"no volume spike (z={vol_zscore:.1f}, ratio={vol_ratio:.1f})")
            direction = Direction.LONG if change_3 > 0 else Direction.SHORT
            entry = last_close
            sl = entry - self.cfg.sl_points * 0.01 if direction == Direction.LONG else entry + self.cfg.sl_points * 0.01
            tp = entry + self.cfg.tp_points * 0.01 if direction == Direction.LONG else entry - self.cfg.tp_points * 0.01
            return Signal(
                direction=direction,
                confidence=45.0,
                reasons=[f"price {direction.value} {abs(change_3):.3f}% over 3 bars (no volume spike, momentum fallback)",
                         f"Vol: {last_vol:.0f} (avg {last_vol_avg:.0f}, z={vol_zscore:.1f}, ratio={vol_ratio:.1f})"],
                htf_bias="NEUTRAL",
                entry=round(entry, 2),
                stop_loss=round(sl, 2),
                take_profit=round(tp, 2),
                rr=round(abs(tp - entry) / max(abs(entry - sl), 1e-9), 2),
                metadata={"strategy": "tick_scalper", "last_close": last_close, "symbol": symbol},
                timestamp=time.time(),
            )

        if abs(momentum_atr) < self.cfg.momentum_threshold:
            return self._neutral(f"spike but no momentum ({momentum_atr:.2f} ATR)")

        confidence = 50.0
        reasons: list[str] = [
            f"Volume: {last_vol:.0f} (avg {last_vol_avg:.0f}, z={vol_zscore:.1f}, ratio={vol_ratio:.1f})",
            f"Price momentum: {momentum:+.2f} ({momentum_atr:+.2f} ATR over {self.cfg.momentum_bars} bars)",
        ]
        if not is_spike:
            reasons.append("moderate volume increase (mild spike)")

        if momentum_atr > 0:
            direction = Direction.LONG
            entry = float(close.iloc[-1])
            sl = entry - self.cfg.sl_points * 0.01
            tp = entry + self.cfg.tp_points * 0.01
            if vol_zscore > 3.0:
                confidence += 20
                reasons.append("extreme volume spike (z>3)")
            elif vol_zscore > 2.5:
                confidence += 10
                reasons.append("strong volume spike (z>2.5)")
            else:
                confidence += 5
            if momentum_atr > 1.0:
                confidence += 10
                reasons.append("strong momentum (>1 ATR)")
        else:
            direction = Direction.SHORT
            entry = float(close.iloc[-1])
            sl = entry + self.cfg.sl_points * 0.01
            tp = entry - self.cfg.tp_points * 0.01
            if vol_zscore > 3.0:
                confidence += 20
                reasons.append("extreme volume spike (z>3)")
            elif vol_zscore > 2.5:
                confidence += 10
                reasons.append("strong volume spike (z>2.5)")
            else:
                confidence += 5
            if abs(momentum_atr) > 1.0:
                confidence += 10
                reasons.append("strong downward momentum (>1 ATR)")

        reasons.append(f"ATR = {last_atr:.2f}")
        confidence = float(np.clip(confidence, 0, 100))

        if confidence < self.cfg.min_confidence:
            return self._neutral(f"confidence {confidence:.0f}% < {self.cfg.min_confidence}%")

        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = reward / max(risk, 1e-9)
        if rr < self.cfg.min_rr:
            return self._neutral(f"R:R {rr:.2f} < {self.cfg.min_rr}")

        # Update last signal bar
        self._last_signal_bar = current_bar

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
                "volume": last_vol,
                "volume_zscore": vol_zscore,
                "volume_ratio": vol_ratio,
                "momentum": momentum,
                "momentum_atr": momentum_atr,
                "atr": last_atr,
                "last_close": float(close.iloc[-1]),
                "symbol": symbol,
                "strategy": "tick_scalper",
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
            metadata={"strategy": "tick_scalper"},
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
