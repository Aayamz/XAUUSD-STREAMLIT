"""Position sizing utilities.

Lot sizing is derived from:
    risk_amount = equity * risk_pct
    sl_distance_price = abs(entry - stop_loss)
    tick_value      = contract_size * point        (e.g. 100 * 0.01 = 1 USD per 0.01 / lot)
    sl_distance_ticks = sl_distance_price / point
    lots = risk_amount / (sl_distance_ticks * tick_value)
"""
from __future__ import annotations

import math
from typing import Any

from utils.config import get_config


def contract_specs(symbol_info: dict[str, Any]) -> dict[str, float]:
    return {
        "point": float(symbol_info.get("point") or 0.01),
        "contract_size": float(symbol_info.get("contract_size") or 100.0),
        "volume_min": float(symbol_info.get("volume_min") or 0.01),
        "volume_max": float(symbol_info.get("volume_max") or 100.0),
        "volume_step": float(symbol_info.get("volume_step") or 0.01),
        "digits": int(symbol_info.get("digits") or 2),
    }


def compute_lot_size(
    equity: float,
    entry: float,
    stop_loss: float,
    symbol_info: dict[str, Any],
    risk_pct: float | None = None,
) -> float:
    cfg = get_config().get("risk", {})
    risk_pct = risk_pct if risk_pct is not None else float(cfg.get("account_risk_pct", 1.0))
    spec = contract_specs(symbol_info)

    risk_amount = equity * (risk_pct / 100.0)
    sl_distance = abs(entry - stop_loss)
    if sl_distance <= 0:
        return spec["volume_min"]

    tick_value = spec["contract_size"] * spec["point"]
    sl_ticks = sl_distance / spec["point"]
    raw_lots = risk_amount / (sl_ticks * tick_value)
    # round to nearest volume_step
    step = spec["volume_step"]
    lots = math.floor(raw_lots / step) * step
    lots = max(spec["volume_min"], min(lots, spec["volume_max"]))
    # also respect configured max lot
    max_lot = float(cfg.get("max_lot_size", 1.0))
    lots = min(lots, max_lot)
    return round(lots, 2)
