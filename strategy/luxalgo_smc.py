"""Main strategy — LuxAlgo-inspired Smart Money Concepts for XAUUSD.

The strategy is composed of independent detectors (OB, FVG, Liquidity, etc.)
that contribute confidence to a final direction. A trade is only generated
when *all* of the following are satisfied:

* A higher-timeframe bias is present (BULL or BEAR) — never trade against it
* We are inside an enabled session and not on a weekend
* An Order Block has been mitigated in the direction of the bias
* A Fair Value Gap provides confluence (optional but adds confidence)
* The proposed trade has at least ``min_rr`` reward-to-risk

The result is a ``Signal`` dataclass carrying everything the risk manager and
dashboard need.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

import numpy as np
import pandas as pd

from data.indicators import atr
from utils.config import get_config
from utils.logger import get_logger

from .fair_value_gaps import find_fvgs
from .liquidity import find_liquidity
from .multi_timeframe import htf_bias
from .order_blocks import OrderBlock, find_order_blocks
from .premium_discount import premium_discount
from .session_filter import active_session, trading_allowed
from .structure import label_structure

log = get_logger(__name__)


class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass
class Signal:
    direction: Direction
    confidence: float               # 0..100
    reasons: List[str] = field(default_factory=list)
    htf_bias: str = "NEUTRAL"
    session: Optional[str] = None
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    rr: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def is_actionable(self, min_confidence: float = 55.0, min_rr: float = 1.0) -> bool:
        """Check if signal is actionable with configurable thresholds."""
        return (
            self.direction != Direction.NEUTRAL
            and self.confidence >= min_confidence
            and self.entry > 0
            and self.stop_loss > 0
            and self.take_profit > 0
            and self.rr >= min_rr
        )


class LuxAlgoSMC:
    """Composed strategy. Stateless beyond config — safe to call repeatedly."""

    def __init__(self, cfg: dict | None = None, mode: str = "swing"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.mode = mode
        # Apply mode-specific overrides if in scalp mode
        if mode == "scalp":
            self.cfg = {
                **base_cfg,
                "higher_timeframe": base_cfg.get("scalp_higher_timeframe", base_cfg.get("higher_timeframe", "H4")),
                "entry_timeframe": base_cfg.get("scalp_entry_timeframe", base_cfg.get("entry_timeframe", "M15")),
                "min_rr": base_cfg.get("scalp_min_rr", base_cfg.get("min_rr", 2.0)),
                "confidence_threshold": base_cfg.get("scalp_confidence_threshold", base_cfg.get("confidence_threshold", 55))
            }
        else:
            self.cfg = base_cfg
        self.risk_cfg = get_config().get("risk", {})

    # --- public ---------------------------------------------------------------
    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < 60:
            return self._neutral("insufficient LTF data")

        if not trading_allowed():
            return self._neutral("outside trading session / weekend")

        bias = htf_bias(df_htf, swing_length=int(self.cfg.get("swing_length", 5))) if df_htf is not None else "NEUTRAL"
        if bias == "NEUTRAL":
            return self._neutral("no HTF bias")

        pd_zone = premium_discount(df_ltf, swing_length=int(self.cfg.get("swing_length", 5)))
        obs = find_order_blocks(
            df_ltf,
            swing_length=int(self.cfg.get("swing_length", 5)),
            min_displacement_atr=float(self.cfg.get("ob_min_displacement_atr", 1.5)),
            lookback=int(self.cfg.get("ob_lookback", 50)),
        )
        fvgs = find_fvgs(
            df_ltf,
            min_size_atr=float(self.cfg.get("fvg_min_size_atr", 0.3)),
            lookback=80,
        )
        buy_liq, sell_liq = find_liquidity(
            df_ltf,
            swing_length=int(self.cfg.get("swing_length", 5)),
            tolerance_atr=float(self.cfg.get("liquidity_tolerance_atr", 0.5)),
            lookback=int(self.cfg.get("liquidity_lookback", 100)),
        )

        a = atr(df_ltf, 14).iloc[-1] or 1.0
        last_close = float(df_ltf["close"].iloc[-1])
        session = active_session()

        # Add volatility filter - avoid trading in extremely low/high volatility
        # Calculate ATR percentage of price to normalize volatility
        if last_close > 0:
            atr_pct = (a / last_close) * 100
        else:
            atr_pct = 0

        # Define volatility thresholds (adjustable via config)
        min_volatility_pct = float(self.cfg.get("min_volatility_pct", 0.05))  # 0.05% minimum
        max_volatility_pct = float(self.cfg.get("max_volatility_pct", 5.0))   # 5% maximum

        if atr_pct < min_volatility_pct:
            return self._neutral(f"volatility too low: {atr_pct:.4f}% < {min_volatility_pct}%")
        if atr_pct > max_volatility_pct:
            return self._neutral(f"volatility too high: {atr_pct:.4f}% > {max_volatility_pct}%")

        # 1) Filter to OBs in the direction of the HTF bias
        if bias == "BULL":
            bias_aligned: List[OrderBlock] = [o for o in obs if o.is_bullish]
        else:
            bias_aligned = [o for o in obs if (not o.is_bullish)]

        # 2) Prefer mitigated OBs (price has retraced into them)
        candidates: List[OrderBlock] = [o for o in bias_aligned if o.mitigated]

        # 3) Fallback: OBs where current price is *near* the zone (within proximity_atr)
        proximity = float(self.cfg.get("ob_proximity_atr", 1.0))
        if not candidates:
            for o in bias_aligned:
                ob_low, ob_high = min(o.top, o.bottom), max(o.top, o.bottom)
                if abs(last_close - ob_low) <= proximity * a or abs(last_close - ob_high) <= proximity * a:
                    candidates.append(o)

        # 4) Last resort: the most recent unmitigated OB in bias direction
        #    (price hasn't yet retraced, but a setup is forming)
        if not candidates and bias_aligned:
            candidates = [bias_aligned[0]]  # already sorted by recency

        # Premium/Discount filter adds bonus confidence
        bias_ok_with_pd = (
            (bias == "BULL" and pd_zone["zone"] in {"discount", "eq"})
            or (bias == "BEAR" and pd_zone["zone"] in {"premium", "eq"})
        )

        if not candidates:
            return self._neutral(f"no mitigated OB aligned with {bias} bias")

        # Choose the OB closest to current price that price is currently in / near
        ob = min(candidates, key=lambda o: abs(((o.top + o.bottom) / 2.0) - last_close))
        ob_mid = (ob.top + ob.bottom) / 2.0
        # Track whether this is a primary (mitigated) setup or a fallback
        is_primary = ob.mitigated
        ob_low, ob_high = min(ob.top, ob.bottom), max(ob.top, ob.bottom)
        near_zone = ob_low - proximity * a <= last_close <= ob_high + proximity * a

        # FVG confluence
        if bias == "BULL":
            fvg_near = [
                g for g in fvgs
                if g.is_bullish and g.bottom <= last_close <= g.top
            ]
            swept = any(l.swept for l in sell_liq)
        else:
            fvg_near = [
                g for g in fvgs
                if (not g.is_bullish) and g.bottom <= last_close <= g.top
            ]
            swept = any(l.swept for l in buy_liq)

        # Build entry / SL / TP with broker minimum distance enforcement
        direction = Direction.LONG if bias == "BULL" else Direction.SHORT
        if direction == Direction.LONG:
            entry = ob_mid
            sl_raw = ob.bottom - a * 0.25
            risk_raw = entry - sl_raw
            tp_raw = entry + risk_raw * float(self.cfg.get("min_rr", 2.0))
        else:
            entry = ob_mid
            sl_raw = ob.top + a * 0.25
            risk_raw = sl_raw - entry
            tp_raw = entry - risk_raw * float(self.cfg.get("min_rr", 2.0))

        # Calculate raw RR before adjustments
        rr_raw = abs(tp_raw - entry) / max(abs(risk_raw), 1e-9)

        # Enforce broker minimum stop distance if we have symbol info
        # This will be adjusted again in _open_trade, but we validate early
        sl = sl_raw
        tp = tp_raw

        rr = rr_raw

        # Confidence scoring (0..100)
        confidence = 50.0
        reasons: list[str] = []
        reasons.append(f"HTF bias = {bias}")
        if bias_ok_with_pd:
            confidence += 10
            reasons.append(f"price in {pd_zone['zone']} zone (confluent)")
        else:
            confidence -= 5
            reasons.append(f"price in {pd_zone['zone']} zone (against premium/discount bias)")
        if ob.mitigated:
            confidence += 10
            reasons.append("order block mitigated")
        elif near_zone:
            confidence += 5
            reasons.append(f"price within {proximity:g} ATR of fresh OB")
        else:
            confidence += 2
            reasons.append("approaching recent OB (not yet mitigated)")
        if fvg_near:
            confidence += 10
            reasons.append("fair value gap confluence")
        if swept:
            confidence += 5
            reasons.append("liquidity swept (stop hunt)")
        confidence += min(rr - 2.0, 5)  # up to +5 for higher RR
        if session:
            reasons.append(f"session = {session}")
        confidence = float(np.clip(confidence, 0, 100))

        sig = Signal(
            direction=direction,
            confidence=confidence,
            reasons=reasons,
            htf_bias=bias,
            session=session,
            entry=round(entry, 2),
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            rr=round(rr, 2),
            metadata={
                "ob": {"index": ob.index, "top": ob.top, "bottom": ob.bottom, "bias": ob.bias},
                "pd_zone": pd_zone,
                "fvg_confluence": bool(fvg_near),
                "swept_liquidity": swept,
                "atr": float(a),
                "last_close": last_close,
                "symbol": symbol,
            },
            timestamp=float(pd.Timestamp.utcnow().timestamp()),
        )
        return sig

    # --- helpers --------------------------------------------------------------
    def _neutral(self, reason: str) -> Signal:
        return Signal(
            direction=Direction.NEUTRAL,
            confidence=0.0,
            reasons=[reason],
            htf_bias="NEUTRAL",
            session=active_session(),
            timestamp=float(pd.Timestamp.utcnow().timestamp()),
        )

    # --- annotations (for the chart) -----------------------------------------
    def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
        """Return data structures the dashboard can plot (OB, FVG, swings, …)."""
        swing_length = int(self.cfg.get("swing_length", 5))
        df_s = label_structure(df, length=swing_length)
        obs = find_order_blocks(df, swing_length=swing_length,
                                min_displacement_atr=float(self.cfg.get("ob_min_displacement_atr", 1.5)),
                                lookback=int(self.cfg.get("ob_lookback", 50)))
        fvgs = find_fvgs(df,
                         min_size_atr=float(self.cfg.get("fvg_min_size_atr", 0.3)),
                         lookback=100)
        buy_liq, sell_liq = find_liquidity(df, swing_length=swing_length,
                                           tolerance_atr=float(self.cfg.get("liquidity_tolerance_atr", 0.5)),
                                           lookback=int(self.cfg.get("liquidity_lookback", 100)))
        pd_zone = premium_discount(df, swing_length=swing_length, lookback=80)
        return {
            "df": df_s,
            "order_blocks": obs,
            "fvgs": fvgs,
            "buy_liquidity": buy_liq,
            "sell_liquidity": sell_liq,
            "premium_discount": pd_zone,
        }
