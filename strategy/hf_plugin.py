"""Generic HuggingFace Model Plug-in Interface.

Allows users to plug in any HuggingFace model and wrap it as a trading
strategy.  Supports both classification models (buy/sell/hold) and
regression models (predict price direction/magnitude).

Usage from dashboard:
    plugin = HFPlugin.from_repo("user/repo-name", model_file="model.joblib")
    strategy = plugin.to_strategy(name="my_strategy", cfg=config)

Or register directly:
    plugin = HFPlugin.from_repo("user/repo", model_file="model.joblib")
    plugin.register(name="custom_smc")
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import numpy as np
import pandas as pd

from data.indicators import add_indicators, atr, ema, rsi
from strategy.luxalgo_smc import Direction, Signal
from strategy import register_strategy
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)

try:
    from huggingface_hub import hf_hub_download, list_repo_files
    _HF_AVAILABLE = True
except ImportError:
    hf_hub_download = None  # type: ignore[assignment]
    list_repo_files = None  # type: ignore[assignment]
    _HF_AVAILABLE = False

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    joblib = None  # type: ignore[assignment]
    _JOBLIB_AVAILABLE = False

try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False


_PLUGIN_DIR = Path(__file__).resolve().parent.parent / "models" / "hf_plugins"


@dataclass
class HFPlugin:
    """Configures a HuggingFace model to be used as a trading strategy."""

    repo_id: str
    model_file: str
    model_type: str = "joblib"  # joblib | pytorch | onnx | keras
    feature_columns: list[str] = field(default_factory=list)
    predict_method: str = "predict_proba"  # predict_proba | predict | forward
    input_shape: tuple | None = None
    label_map: dict[int, str] = field(default_factory=lambda: {0: "SHORT", 1: "LONG", 2: "HOLD"})
    lookback_bars: int = 200
    timeframe: str = "M5"

    # Strategy parameters (defaults from HF scalping model)
    tp_points: int = 100
    sl_points: int = 50
    min_confidence: float = 55.0
    min_rr: float = 1.0

    # Internal state
    _model: Any = field(default=None, repr=False)
    _loaded: bool = field(default=False, repr=False)

    @classmethod
    def from_repo(
        cls,
        repo_id: str,
        model_file: str = "model.joblib",
        *,
        model_type: str = "joblib",
        feature_columns: list[str] | None = None,
        label_map: dict[int, str] | None = None,
        tp_points: int = 100,
        sl_points: int = 50,
        **kwargs,
    ) -> HFPlugin:
        """Create a plugin from a HuggingFace repo."""
        return cls(
            repo_id=repo_id,
            model_file=model_file,
            model_type=model_type,
            feature_columns=feature_columns or [],
            label_map=label_map or {0: "SHORT", 1: "LONG", 2: "HOLD"},
            tp_points=tp_points,
            sl_points=sl_points,
            **kwargs,
        )

    @classmethod
    def from_local(cls, model_path: str, **kwargs) -> HFPlugin:
        """Create a plugin from a local model file."""
        plugin = cls(repo_id="", model_file=model_path, **kwargs)
        plugin._load_local(Path(model_path))
        return plugin

    def _load_local(self, path: Path) -> Any:
        if self._loaded:
            return self._model
        try:
            if self.model_type == "joblib" and _JOBLIB_AVAILABLE:
                self._model = joblib.load(path)
            elif self.model_type == "pytorch" and _TORCH_AVAILABLE:
                self._model = torch.load(path, map_location="cpu")
                self._model.eval()
            else:
                raise ImportError(f"Cannot load {self.model_type} model")
            self._loaded = True
            log.info("Loaded local model: %s", path)
        except Exception as e:
            log.error("Failed to load model %s: %s", path, e)
            raise
        return self._model

    def load_model(self) -> Any:
        """Download and load the model from HuggingFace Hub."""
        if self._loaded:
            return self._model
        if not _HF_AVAILABLE:
            raise ImportError("huggingface_hub is required. Install with: pip install huggingface_hub")
        if not self.repo_id:
            raise ValueError("No repo_id set. Use from_repo() or from_local().")

        _PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        try:
            path = hf_hub_download(
                repo_id=self.repo_id,
                filename=self.model_file,
                local_dir=str(_PLUGIN_DIR),
            )
            return self._load_local(Path(path))
        except Exception as e:
            log.error("Failed to download model from %s: %s", self.repo_id, e)
            raise

    def predict(self, features: pd.DataFrame) -> dict[str, Any]:
        """Run prediction and return structured result."""
        model = self.load_model()
        result = {"prediction": None, "confidence": 0.0, "raw": None}

        try:
            if self.model_type == "pytorch" and _TORCH_AVAILABLE:
                tensor = torch.tensor(features.values, dtype=torch.float32)
                with torch.no_grad():
                    output = model(tensor)
                if hasattr(output, "softmax"):
                    probs = output.softmax(dim=-1).numpy()[0]
                else:
                    probs = output.numpy()[0]
                pred_idx = int(np.argmax(probs))
                result["prediction"] = self.label_map.get(pred_idx, str(pred_idx))
                result["confidence"] = float(probs[pred_idx])
                result["raw"] = probs.tolist()
            else:
                # sklearn-style models
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(features)
                    pred_idx = int(np.argmax(proba[0]))
                    result["prediction"] = self.label_map.get(pred_idx, str(pred_idx))
                    result["confidence"] = float(proba[0][pred_idx])
                    result["raw"] = proba[0].tolist()
                elif hasattr(model, "predict"):
                    pred = model.predict(features)[0]
                    result["prediction"] = self.label_map.get(int(pred), str(pred))
                    result["confidence"] = 0.7  # no probability available
                    result["raw"] = str(pred)
        except Exception as e:
            log.warning("Prediction error: %s", e)

        return result

    def build_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build feature matrix from OHLCV DataFrame.

        If feature_columns is set, only those columns are used.
        Otherwise, a standard feature set is generated.
        """
        df_ind = add_indicators(df)
        feat = pd.DataFrame(index=df_ind.index)

        if self.feature_columns:
            for col in self.feature_columns:
                if col in df_ind.columns:
                    feat[col] = df_ind[col]
        else:
            close = df_ind["close"]
            feat["return_1"] = close.pct_change(1)
            feat["return_5"] = close.pct_change(5)
            feat["return_10"] = close.pct_change(10)
            feat["ema5"] = ema(close, 5)
            feat["ema20"] = ema(close, 20)
            feat["ema50"] = ema(close, 50)
            feat["rsi14"] = rsi(close, 14)
            feat["atr14"] = atr(df_ind, 14)
            feat["volatility"] = close.rolling(20).std()
            feat["high_low_range"] = (df_ind["high"] - df_ind["low"]) / close
            feat["close_open_range"] = (close - df_ind["open"]) / close

        feat = feat.dropna()
        return feat

    def to_strategy(self, name: str, cfg: dict | None = None, mode: str = "scalp"):
        """Wrap this plugin as a strategy class and return an instance."""

        plugin = self

        class _PluginStrategy:
            """Auto-generated strategy wrapping a HuggingFace model."""

            def __init__(self, cfg: dict | None = None, mode: str = "scalp"):
                self.cfg = cfg or {}
                self.mode = mode
                self._plugin = plugin
                self.name = name

            def generate_signal(
                self,
                df_ltf: pd.DataFrame,
                df_htf: pd.DataFrame | None = None,
                symbol: str = "XAUUSD",
            ) -> Signal:
                if df_ltf is None or len(df_ltf) < 30:
                    return self._neutral("insufficient data")

                features = self._plugin.build_features(df_ltf)
                if features.empty:
                    return self._neutral("no features computed")

                result = self._plugin.predict(features.iloc[[-1]])
                pred = result.get("prediction")
                conf = result.get("confidence", 0.0)

                if pred is None or pred == "HOLD":
                    return self._neutral("model predicts HOLD")

                last_close = float(df_ltf["close"].iloc[-1])
                last_atr = float(atr(df_ltf, 14).iloc[-1]) or 1.0

                if pred == "LONG":
                    direction = Direction.LONG
                    entry = last_close
                    sl = entry - plugin.sl_points * 0.01
                    tp = entry + plugin.tp_points * 0.01
                elif pred == "SHORT":
                    direction = Direction.SHORT
                    entry = last_close
                    sl = entry + plugin.sl_points * 0.01
                    tp = entry - plugin.tp_points * 0.01
                else:
                    return self._neutral(f"unknown prediction: {pred}")

                risk = abs(entry - sl)
                reward = abs(tp - entry)
                rr = reward / max(risk, 1e-9)

                if rr < plugin.min_rr:
                    return self._neutral(f"R:R {rr:.2f} < {plugin.min_rr}")

                confidence = float(np.clip(conf * 100, 0, 100))
                if confidence < plugin.min_confidence:
                    return self._neutral(f"confidence {confidence:.0f}% < {plugin.min_confidence}%")

                reasons = [
                    f"model prediction = {pred}",
                    f"model confidence = {conf:.0%}",
                    f"ATR = {last_atr:.2f}",
                ]
                if df_htf is not None and len(df_htf) >= 50:
                    htf_close = df_htf["close"]
                    htf_f = ema(htf_close, 10)
                    htf_s = ema(htf_close, 30)
                    htf_bias = "BULL" if float(htf_f.iloc[-1]) > float(htf_s.iloc[-1]) else "BEAR"
                    reasons.append(f"HTF bias = {htf_bias}")
                else:
                    htf_bias = "NEUTRAL"

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
                        "model": plugin.repo_id or plugin.model_file,
                        "prediction": pred,
                        "ml_confidence": conf,
                        "last_close": last_close,
                        "atr": last_atr,
                        "symbol": symbol,
                        "strategy": name,
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
                    metadata={"strategy": name},
                )

            def annotate(self, df: pd.DataFrame) -> dict[str, Any]:
                """No special annotations for plugin strategies."""
                return {
                    "df": df,
                    "order_blocks": [],
                    "fvgs": [],
                    "buy_liquidity": [],
                    "sell_liquidity": [],
                    "premium_discount": {},
                }

        return _PluginStrategy(cfg=cfg, mode=mode)

    def register(self, name: str, **kwargs):
        """Register this plugin as a strategy in the global registry."""
        strategy_cls = self.to_strategy(name, **kwargs)
        register_strategy(
            name,
            strategy_cls.__class__,
            label=f"HF Plugin: {self.repo_id or Path(self.model_file).stem}",
            description=f"Custom HuggingFace model from {self.repo_id}",
            modes=["scalp"],
            icon="hf-plugin",
        )
        log.info("Registered HF plugin strategy: %s", name)


# --- Preset models from the community ---
PRESET_MODELS = {
    "xauusd_scalping": {
        "repo_id": "JonusNattapong/xauusd-scalping-models",
        "model_file": "entry_clf.joblib",
        "model_type": "joblib",
        "tp_points": 1500,
        "sl_points": 400,
        "label": "XAUUSD Scalping (entry_clf)",
    },
    "xauusd_xgboost": {
        "repo_id": "JonusNattapong/xauusd-scalping-models",
        "model_file": "xgb.model",
        "model_type": "joblib",
        "tp_points": 1500,
        "sl_points": 400,
        "label": "XAUUSD XGBoost",
    },
}


def list_presets() -> dict[str, dict]:
    """Return available preset model configurations."""
    return PRESET_MODELS.copy()


def load_preset(name: str, **overrides) -> HFPlugin:
    """Load a preset model configuration."""
    if name not in PRESET_MODELS:
        raise ValueError(f"Unknown preset: {name}. Available: {list(PRESET_MODELS.keys())}")
    cfg = {**PRESET_MODELS[name], **overrides}
    # Remove display-only keys that are not HFPlugin parameters
    cfg.pop("label", None)
    return HFPlugin.from_repo(**cfg)
