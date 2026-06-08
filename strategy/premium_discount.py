"""Premium / Discount zones (LuxAlgo arrays)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .structure import find_swings


def premium_discount(df: pd.DataFrame, swing_length: int = 5, lookback: int = 50) -> dict:
    """Compute the premium/discount equilibrium over the recent swing range.

    Returns a dict with ``high``, ``low``, ``eq`` (50%), ``zone`` (premium / discount / eq).
    """
    sh, sl = find_swings(df, length=swing_length)
    sub_h = [s for s in sh if s.index >= len(df) - lookback]
    sub_l = [s for s in sl if s.index >= len(df) - lookback]
    if not sub_h or not sub_l:
        return {"high": np.nan, "low": np.nan, "eq": np.nan, "zone": "eq"}
    hi = max(s.price for s in sub_h)
    lo = min(s.price for s in sub_l)
    eq = (hi + lo) / 2.0
    last = df["close"].iloc[-1]
    if last > eq:
        zone = "premium"
    elif last < eq:
        zone = "discount"
    else:
        zone = "eq"
    return {"high": float(hi), "low": float(lo), "eq": float(eq), "zone": zone}
