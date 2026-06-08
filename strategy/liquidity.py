"""Liquidity levels — equal highs/lows and recent stops swept.

Equal highs/lows: at least two swing points within ``tolerance_atr`` of each
other. Swept liquidity: a wick beyond a swing extreme followed by a close back
inside the range.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd

from data.indicators import atr
from .structure import find_swings


@dataclass
class LiquidityLevel:
    price: float
    is_high: bool
    swept: bool = False
    count: int = 2


def find_liquidity(
    df: pd.DataFrame,
    swing_length: int = 5,
    tolerance_atr: float = 0.5,
    lookback: int = 100,
) -> tuple[List[LiquidityLevel], List[LiquidityLevel]]:
    """Return (buy_side_liquidity, sell_side_liquidity) levels."""
    sh, sl = find_swings(df, length=swing_length)
    a = atr(df, 14).iloc[-1] or 1.0
    tol = a * tolerance_atr

    def cluster(points: list, is_high: bool) -> List[LiquidityLevel]:
        pts = sorted(points, key=lambda p: p.price)
        clusters: List[LiquidityLevel] = []
        for p in pts:
            if p.index < len(df) - lookback:
                continue
            matched = False
            for c in clusters:
                if abs(c.price - p.price) <= tol:
                    c.count += 1
                    matched = True
                    break
            if not matched:
                clusters.append(
                    LiquidityLevel(price=p.price, is_high=is_high, count=1)
                )
        return [c for c in clusters if c.count >= 2]

    buy_liq = cluster(sh, is_high=True)   # stops above these highs
    sell_liq = cluster(sl, is_high=False) # stops below these lows

    # Mark swept
    for lvl in buy_liq:
        for i in range(int(min([p.index for p in sh] or [0])), len(df)):
            if df["high"].iloc[i] > lvl.price and df["close"].iloc[i] < lvl.price:
                lvl.swept = True
                break
    for lvl in sell_liq:
        for i in range(int(min([p.index for p in sl] or [0])), len(df)):
            if df["low"].iloc[i] < lvl.price and df["close"].iloc[i] > lvl.price:
                lvl.swept = True
                break

    return buy_liq, sell_liq
