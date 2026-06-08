"""Strategy registry and factory.

All strategies implement the same interface:
    generate_signal(df_ltf, df_htf=None, symbol="XAUUSD") -> Signal
    annotate(df) -> dict (optional, for chart visualization)

Register new strategies via ``register_strategy()`` or the
``@register`` decorator.  Retrieve them with ``get_strategy_class()``
or instantiate directly via ``create_strategy()``.
"""
from __future__ import annotations

from typing import Any, Dict, Type

from utils.logger import get_logger

log = get_logger(__name__)

_REGISTRY: Dict[str, dict[str, Any]] = {}


def register_strategy(
    name: str,
    cls: Type | None = None,
    *,
    label: str = "",
    description: str = "",
    modes: list[str] | None = None,
    icon: str = "",
):
    """Register a strategy class.  Can be used as a decorator or called directly."""

    def _wrap(cls_inner: Type) -> Type:
        _REGISTRY[name] = {
            "class": cls_inner,
            "label": label or name,
            "description": description,
            "modes": modes or ["swing", "scalp"],
            "icon": icon,
        }
        log.debug("Registered strategy: %s (%s)", name, label)
        return cls_inner

    if cls is not None:
        return _wrap(cls)
    return _wrap


def get_strategy_class(name: str) -> Type | None:
    entry = _REGISTRY.get(name)
    return entry["class"] if entry else None


def list_strategies() -> list[dict[str, Any]]:
    """Return metadata for all registered strategies."""
    return [
        {"name": k, **v, "class": v["class"]}
        for k, v in _REGISTRY.items()
    ]


def get_strategy_info(name: str) -> dict[str, Any] | None:
    entry = _REGISTRY.get(name)
    if entry is None:
        return None
    return {"name": name, **entry}


def available_strategies_for_mode(mode: str) -> list[dict[str, Any]]:
    """Return strategies that support the given mode (swing/scalp)."""
    return [
        {"name": k, **v, "class": v["class"]}
        for k, v in _REGISTRY.items()
        if mode in v.get("modes", [])
    ]


def create_strategy(name: str, cfg: dict | None = None, mode: str = "swing"):
    """Instantiate a registered strategy by name."""
    cls = get_strategy_class(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name!r}. Available: {list(_REGISTRY.keys())}")
    return cls(cfg=cfg, mode=mode)


# --- Import built-in strategies to register them ---
from strategy.luxalgo_smc import LuxAlgoSMC  # noqa: E402, F401
from strategy.hf_scalping import HFScalpingStrategy  # noqa: E402, F401
from strategy.ema_crossover import EMACrossoverScalper  # noqa: E402, F401
from strategy.bollinger_bounce import BollingerBounceScalper  # noqa: E402, F401
from strategy.rsi_stoch import RSIStochasticScalper  # noqa: E402, F401
from strategy.grid_scalper import GridScalper  # noqa: E402, F401
from strategy.tick_scalper import TickScalper  # noqa: E402, F401
from strategy.macd_zero_line import MACDZeroLineScalper  # noqa: E402, F401

register_strategy(
    "luxalgo_smc",
    LuxAlgoSMC,
    label="LuxAlgo SMC",
    description="Smart Money Concepts — order blocks, FVGs, liquidity sweeps, BOS/CHoCH",
    modes=["swing", "scalp"],
    icon="smart-money",
)

register_strategy(
    "hf_scalping",
    HFScalpingStrategy,
    label="HF MA Crossover Scalper",
    description="Hybrid MA(5)/MA(20) crossover with optional ML confirmation. From HuggingFace.",
    modes=["scalp"],
    icon="ml-scalp",
)

register_strategy(
    "ema_crossover",
    EMACrossoverScalper,
    label="EMA Crossover Scalper",
    description="Pure EMA(5)/EMA(20) crossover. Buys on bullish cross, sells on bearish cross. M1/M5.",
    modes=["scalp"],
    icon="ema-cross",
)

register_strategy(
    "bollinger_bounce",
    BollingerBounceScalper,
    label="Bollinger Band Bounce",
    description="Mean reversion at BB bands with RSI filter. Best on ranging markets.",
    modes=["scalp"],
    icon="bb-bounce",
)

register_strategy(
    "rsi_stoch",
    RSIStochasticScalper,
    label="RSI + Stochastic Combo",
    description="RSI(14) + Stochastic dual confirmation. Quick 5-10pt targets.",
    modes=["scalp"],
    icon="rsi-stoch",
)

register_strategy(
    "grid_scalper",
    GridScalper,
    label="Grid Scalper",
    description="Places buy/sell orders at fixed intervals. Profits from oscillation, not direction.",
    modes=["scalp"],
    icon="grid",
)

register_strategy(
    "tick_scalper",
    TickScalper,
    label="Tick / News Scalper",
    description="Fires on volume spikes (news events). Tight TP/SL, fast execution required.",
    modes=["scalp"],
    icon="tick",
)

register_strategy(
    "macd_zero_line",
    MACDZeroLineScalper,
    label="MACD Zero-Line Scalper",
    description="Trades MACD zero-line crossovers on M1/M5. ATR-based dynamic SL/TP.",
    modes=["scalp"],
    icon="macd",
)
