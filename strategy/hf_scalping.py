"""HuggingFace Hybrid MA Crossover Scalping Strategy.

Based on https://huggingface.co/JonusNattapong/xauusd-scalping-models
Combines rule-based MA(5)/MA(20) crossover signals with optional ML model
confirmation.  Works on H1 data with intraday scalping logic.

Core logic:
  - Primary signal: MA(5) vs MA(20) crossover on 1H bars
  - Long:  one position per day, 1000-3000pt targets, SL 400pts
  - Short: multiple intraday, 10-50pt targets, SL 20pts
  - Session focus: London/NYC for liquidity
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
import pandas as pd

from data.indicators import atr, ema, rsi
from strategy import register_strategy
from strategy.luxalgo_smc import Direction, Signal
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)

# Try importing ML dependencies
try:
    from huggingface_hub import hf_hub_download
    _HF_AVAILABLE = True
except ImportError:
    hf_hub_download = None  # type: ignore[assignment]
    _HF_AVAILABLE = False

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    joblib = None  # type: ignore[assignment]
    _JOBLIB_AVAILABLE = False

_REPO_ID = "JonusNattapong/xauusd-scalping-models"
_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "hf_scalping"


@dataclass
class ScalpConfig:
    """Configuration for the HF scalping strategy."""
    # Timeframes
    higher_timeframe: str = "H1"
    entry_timeframe: str = "M5"

    # MA parameters
    fast_period: int = 5
    slow_period: int = 20

    # Long parameters
    long_tp_points: int = 1500
    long_sl_points: int = 400
    long_position_pct: float = 0.02  # 2% of capital

    # Short parameters
    short_tp_points: int = 30
    short_sl_points: int = 20
    short_position_pct: float = 0.02  # 0.02% of capital

    # Risk
    max_daily_loss_pct: float = 2.0
    max_holding_hours_long: int = 24
    max_holding_hours_short: int = 3
    max_drawdown_pct: float = 15.0

    # Confidence
    min_confidence: float = 50.0
    min_rr: float = 1.0

    # ML model
    use_ml_confirmation: bool = False
    model_names: tuple = ("entry_clf.joblib", "xgb.model")

    @classmethod
    def from_config(cls, cfg: dict) -> ScalpConfig:
        sc = cfg.get("scalping", {})
        return cls(
            higher_timeframe=sc.get("higher_timeframe", cfg.get("scalp_higher_timeframe", "H1")),
            entry_timeframe=sc.get("entry_timeframe", cfg.get("scalp_entry_timeframe", "M5")),
            fast_period=int(sc.get("fast_period", 5)),
            slow_period=int(sc.get("slow_period", 20)),
            long_tp_points=int(sc.get("long_tp_points", 1500)),
            long_sl_points=int(sc.get("long_sl_points", 400)),
            long_position_pct=float(sc.get("long_position_pct", 0.02)),
            short_tp_points=int(sc.get("short_tp_points", 30)),
            short_sl_points=int(sc.get("short_sl_points", 20)),
            short_position_pct=float(sc.get("short_position_pct", 0.0002)),
            max_daily_loss_pct=float(sc.get("max_daily_loss_pct", 2.0)),
            max_holding_hours_long=int(sc.get("max_holding_hours_long", 24)),
            max_holding_hours_short=int(sc.get("max_holding_hours_short", 3)),
            max_drawdown_pct=float(sc.get("max_drawdown_pct", 15.0)),
            min_confidence=float(sc.get("min_confidence", 50.0)),
            min_rr=float(sc.get("min_rr", 1.0)),
            use_ml_confirmation=bool(sc.get("use_ml_confirmation", False)),
        )


class _ModelLoader:
    """Lazy-load ML models from HuggingFace Hub."""

    def __init__(self, model_names: tuple, use_ml: bool):
        self._model_names = model_names
        self._use_ml = use_ml
        self._models: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> dict[str, Any]:
        if self._loaded or not self._use_ml:
            return self._models
        if not _HF_AVAILABLE or not _JOBLIB_AVAILABLE:
            log.warning("huggingface_hub/joblib not installed — ML confirmation disabled")
            return self._models

        _MODEL_DIR.mkdir(parents=True, exist_ok=True)
        for name in self._model_names:
            try:
                path = hf_hub_download(
                    repo_id=_REPO_ID,
                    filename=name,
                    local_dir=str(_MODEL_DIR),
                )
                if name.endswith(".joblib") and joblib is not None:
                    self._models[name] = joblib.load(path)
                    log.info("Loaded HF model: %s", name)
            except Exception as e:
                log.warning("Could not load model %s: %s", name, e)
        self._loaded = True
        return self._models

    def predict(self, features: pd.DataFrame) -> dict[str, Any]:
        models = self.load()
        result = {"ml_confidence": 0.0, "ml_signal": None}
        if not models:
            return result

        # Try the entry classifier first
        clf = models.get("entry_clf.joblib") or models.get("xgb.model")
        if clf is not None:
            try:
                proba = clf.predict_proba(features)
                result["ml_confidence"] = float(max(proba[0]))
                result["ml_signal"] = "LONG" if clf.predict(features)[0] == 1 else "SHORT"
            except Exception as e:
                log.debug("ML predict error: %s", e)
        return result


@register_strategy(
    "hf_scalping",
    label="HF MA Crossover Scalper",
    description=(
        "Hybrid MA(5)/MA(20) crossover with optional ML confirmation. "
        "From HuggingFace: JonusNattapong/xauusd-scalping-models"
    ),
    modes=["scalp"],
    icon="ml-scalp",
)
class HFScalpingStrategy:
    """HuggingFace Hybrid MA Crossover Scalping Strategy."""

    def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
        base_cfg = cfg or get_config().get("strategy", {})
        self.cfg = ScalpConfig.from_config(base_cfg)
        self.mode = mode
        self._model_loader = _ModelLoader(
            self.cfg.model_names,
            self.cfg.use_ml_confirmation,
        )

    def generate_signal(
        self,
        df_ltf: pd.DataFrame,
        df_htf: pd.DataFrame | None = None,
        symbol: str = "XAUUSD",
    ) -> Signal:
        if df_ltf is None or len(df_ltf) < self.cfg.slow_period + 10:
            return self._neutral("insufficient data")

        df = df_ltf.copy()
        close = df["close"]

        # --- Indicators ---
        fast_ma = ema(close, self.cfg.fast_period)
        slow_ma = ema(close, self.cfg.slow_period)
        rsi_val = rsi(close, 14)
        atr_val = atr(df, 14)

        last_fast = float(fast_ma.iloc[-1])
        last_slow = float(slow_ma.iloc[-1])
        prev_fast = float(fast_ma.iloc[-2])
        prev_slow = float(slow_ma.iloc[-2])
        last_close = float(close.iloc[-1])
        last_rsi = float(rsi_val.iloc[-1])
        last_atr = float(atr_val.iloc[-1]) if not np.isnan(atr_val.iloc[-1]) else 1.0

        # --- Crossover detection ---
        crossed_up = prev_fast <= prev_slow and last_fast > last_slow
        crossed_down = prev_fast >= prev_slow and last_fast < last_slow
        fast_above = last_fast > last_slow

        # --- MA slope (momentum direction) ---
        fast_slope = last_fast - float(fast_ma.iloc[-3]) if len(fast_ma) >= 3 else 0
        slow_slope = last_slow - float(slow_ma.iloc[-3]) if len(slow_ma) >= 3 else 0

        # --- Recent crossover (within last 3 bars) ---
        recent_cross_up = False
        recent_cross_down = False
        for i in range(-4, -1):
            if len(fast_ma) >= abs(i) + 1:
                f_prev = float(fast_ma.iloc[i - 1])
                s_prev = float(slow_ma.iloc[i - 1])
                f_curr = float(fast_ma.iloc[i])
                s_curr = float(slow_ma.iloc[i])
                if f_prev <= s_prev and f_curr > s_curr:
                    recent_cross_up = True
                if f_prev >= s_prev and f_curr < s_curr:
                    recent_cross_down = True

        # --- HTF bias (if provided) ---
        htf_bias = "NEUTRAL"
        if df_htf is not None and len(df_htf) >= 50:
            htf_close = df_htf["close"]
            htf_fast = ema(htf_close, 10)
            htf_slow = ema(htf_close, 30)
            if float(htf_fast.iloc[-1]) > float(htf_slow.iloc[-1]):
                htf_bias = "BULL"
            elif float(htf_fast.iloc[-1]) < float(htf_slow.iloc[-1]):
                htf_bias = "BEAR"

        # --- ML confirmation ---
        ml_result = {"ml_confidence": 0.0, "ml_signal": None}
        if self.cfg.use_ml_confirmation:
            try:
                features = self._build_features(df)
                ml_result = self._model_loader.predict(features)
            except Exception as e:
                log.debug("ML confirmation failed: %s", e)

        # --- Signal generation ---
        reasons: list[str] = []
        confidence = 50.0
        direction = Direction.NEUTRAL
        entry = 0.0
        sl = 0.0
        tp = 0.0

        # Entry conditions: crossover, recent crossover, or fast trending
        # Trend persistence: count how many of the last 5 bars had fast above slow
        above_count = 0
        below_count = 0
        for i in range(-5, 0):
            if len(fast_ma) >= abs(i) + 1:
                if float(fast_ma.iloc[i]) > float(slow_ma.iloc[i]):
                    above_count += 1
                else:
                    below_count += 1

        # MA separation (normalized by slow MA)
        ma_separation = (last_fast - last_slow) / max(abs(last_slow), 1e-9)

        long_condition = (
            crossed_up
            or recent_cross_up
            or (fast_above and fast_slope > 0)
            or (above_count >= 4)  # 4 of last 5 bars had fast above slow
        )
        short_condition = (
            crossed_down
            or recent_cross_down
            or (not fast_above and fast_slope < 0)
            or (below_count >= 4)  # 4 of last 5 bars had fast below slow
        )

        if long_condition:
            direction = Direction.LONG
            entry = last_close
            sl = entry - self.cfg.long_sl_points * 0.01
            tp = entry + self.cfg.long_tp_points * 0.01
            if crossed_up:
                reasons.append(f"MA({self.cfg.fast_period}) crossed above MA({self.cfg.slow_period})")
            elif recent_cross_up:
                reasons.append(f"recent MA crossover (last 3 bars)")
            else:
                reasons.append(f"fast MA trending above slow MA (bullish alignment)")
            if htf_bias == "BULL":
                confidence += 15
                reasons.append("HTF bias = BULL (confluent)")
            elif htf_bias == "BEAR":
                confidence -= 10
                reasons.append("HTF bias = BEAR (counter-trend)")
            if last_rsi < 35:
                confidence += 10
                reasons.append(f"RSI oversold ({last_rsi:.0f})")
            elif last_rsi < 60:
                confidence += 5
                reasons.append(f"RSI moderate ({last_rsi:.0f})")
            if fast_slope > 0:
                confidence += 5
                reasons.append("fast MA slope positive")
            if last_atr > 0:
                reasons.append(f"ATR = {last_atr:.2f}")

        elif short_condition:
            direction = Direction.SHORT
            entry = last_close
            sl = entry + self.cfg.short_sl_points * 0.01
            tp = entry - self.cfg.short_tp_points * 0.01
            if crossed_down:
                reasons.append(f"MA({self.cfg.fast_period}) crossed below MA({self.cfg.slow_period})")
            elif recent_cross_down:
                reasons.append(f"recent MA crossunder (last 3 bars)")
            else:
                reasons.append(f"fast MA trending below slow MA (bearish alignment)")
            if htf_bias == "BEAR":
                confidence += 15
                reasons.append("HTF bias = BEAR (confluent)")
            elif htf_bias == "BULL":
                confidence -= 10
                reasons.append("HTF bias = BULL (counter-trend)")
            if last_rsi > 65:
                confidence += 10
                reasons.append(f"RSI overbought ({last_rsi:.0f})")
            elif last_rsi > 55:
                confidence += 5
                reasons.append(f"RSI high ({last_rsi:.0f})")
            if fast_slope < 0:
                confidence += 5
                reasons.append("fast MA slope negative")
            if last_atr > 0:
                reasons.append(f"ATR = {last_atr:.2f}")

        else:
            return self._neutral("no MA crossover signal")

        # ML boost
        if ml_result.get("ml_confidence", 0) > 0.6:
            confidence += 10
            reasons.append(f"ML confirms ({ml_result['ml_confidence']:.0%})")
        elif ml_result.get("ml_confidence", 0) > 0:
            reasons.append(f"ML neutral ({ml_result['ml_confidence']:.0%})")

        # R:R check
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        rr = reward / max(risk, 1e-9)
        if rr < self.cfg.min_rr:
            return self._neutral(f"R:R {rr:.2f} < {self.cfg.min_rr} minimum")

        confidence = float(np.clip(confidence, 0, 100))
        if confidence < self.cfg.min_confidence:
            return self._neutral(f"confidence {confidence:.0f}% < {self.cfg.min_confidence}%")

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
                "strategy": "hf_scalping",
                "htf_bias": htf_bias,
                "ml_result": ml_result,
            },
            timestamp=time.time(),
        )

    def _build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build feature matrix for ML model from OHLCV data."""
        close = df["close"]
        feat = pd.DataFrame(index=df.index)
        feat["close"] = close
        feat["return_1"] = close.pct_change(1)
        feat["return_5"] = close.pct_change(5)
        feat["return_10"] = close.pct_change(10)
        feat["ema5"] = ema(close, 5)
        feat["ema20"] = ema(close, 20)
        feat["rsi"] = rsi(close, 14)
        feat["atr"] = atr(df, 14)
        feat["volatility"] = close.rolling(20).std()
        feat = feat.dropna()
        return feat.iloc[[-1]]  # last row only

    def _neutral(self, reason: str) -> Signal:
        return Signal(
            direction=Direction.NEUTRAL,
            confidence=0.0,
            reasons=[reason],
            htf_bias="NEUTRAL",
            timestamp=time.time(),
            metadata={"strategy": "hf_scalping"},
        )

    def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
        """Return chart annotation data (MA lines, crossover markers)."""
        close = df["close"]
        fast_ma = ema(close, self.cfg.fast_period)
        slow_ma = ema(close, self.cfg.slow_period)

        # Detect crossover points for markers
        f = fast_ma.values
        s = slow_ma.values
        cross_up = (f[:-1] <= s[:-1]) & (f[1:] > s[1:])
        cross_down = (f[:-1] >= s[:-1]) & (f[1:] < s[1:])

        # Pad to match DataFrame length
        cross_up = np.concatenate([[False], cross_up])
        cross_down = np.concatenate([[False], cross_down])

        df_out = df.copy()
        df_out["fast_ma"] = fast_ma
        df_out["slow_ma"] = slow_ma
        df_out["cross_up"] = cross_up
        df_out["cross_down"] = cross_down

        return {
            "df": df_out,
            "order_blocks": [],
            "fvgs": [],
            "buy_liquidity": [],
            "sell_liquidity": [],
            "premium_discount": {},
        }
