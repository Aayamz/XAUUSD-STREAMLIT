"""Multi-timeframe bias — analyse HTF to determine direction, LTF for entries."""
from __future__ import annotations

import pandas as pd

from .structure import label_structure


def htf_bias(df_htf: pd.DataFrame, swing_length: int = 5) -> str:
    """Return 'BULL', 'BEAR' or 'NEUTRAL' from the higher timeframe trend."""
    if df_htf is None or len(df_htf) < swing_length * 4:
        return "NEUTRAL"
    df_s = label_structure(df_htf, length=swing_length)
    return df_s["trend"].iloc[-1] or "NEUTRAL"
