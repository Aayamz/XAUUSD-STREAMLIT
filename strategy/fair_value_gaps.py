"""Fair Value Gaps (LuxAlgo style)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from data.indicators import atr


@dataclass
class FairValueGap:
    index: int
    top: float
    bottom: float
    is_bullish: bool
    filled: bool = False


def find_fvgs(df: pd.DataFrame, min_size_atr: float = 0.3, lookback: int = 100) -> List[FairValueGap]:
    """Detect 3-bar FVGs and mark them as filled if price re-enters the gap."""
    if len(df) < 3:
        return []
    a = atr(df, 14).bfill()
    out: List[FairValueGap] = []
    for i in range(2, len(df)):
        h0, l0 = df["high"].iloc[i - 2], df["low"].iloc[i - 2]
        h1, l1 = df["high"].iloc[i - 1], df["low"].iloc[i - 1]
        h2, l2 = df["high"].iloc[i], df["low"].iloc[i]
        atr_i = a.iloc[i]
        if atr_i <= 0:
            continue
        if l0 > h2:  # bullish: gap up
            size = l0 - h2
            if size >= atr_i * min_size_atr:
                out.append(FairValueGap(index=i, top=float(l0), bottom=float(h2), is_bullish=True))
        elif h0 < l2:  # bearish: gap down
            size = l2 - h0
            if size >= atr_i * min_size_atr:
                out.append(FairValueGap(index=i, top=float(l2), bottom=float(h0), is_bullish=False))
    # Mark filled
    for g in out:
        sub = df.iloc[g.index + 1 :]
        if g.is_bullish:
            g.filled = (sub["low"] <= g.top).any()
        else:
            g.filled = (sub["high"] >= g.bottom).any()
    out = [g for g in out if (not g.filled) and g.index >= len(df) - lookback]
    return out
