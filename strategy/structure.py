"""Swing point detection and BOS / CHoCH labelling.

A swing high is a bar whose high is greater than the highs of ``length`` bars
on each side. A swing low is the symmetric case. We then walk the swing
sequence forward and label each new break as either BOS (continuation) or
CHoCH (reversal of the most recent swing trend).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import numpy as np
import pandas as pd


class Trend(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


@dataclass
class SwingPoint:
    index: int
    price: float
    is_high: bool  # True = swing high, False = swing low


def find_swings(df: pd.DataFrame, length: int = 5) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """Return (swing_highs, swing_lows) detected with the given pivot length."""
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    sh: list[SwingPoint] = []
    sl: list[SwingPoint] = []
    for i in range(length, n - length):
        if highs[i] == max(highs[i - length : i + length + 1]):
            sh.append(SwingPoint(index=i, price=float(highs[i]), is_high=True))
        if lows[i] == min(lows[i - length : i + length + 1]):
            sl.append(SwingPoint(index=i, price=float(lows[i]), is_high=False))
    return sh, sl


def label_structure(df: pd.DataFrame, length: int = 5) -> pd.DataFrame:
    """Add columns to df: ``swing_h``, ``swing_l``, ``bos``, ``choch``, ``trend``.

    ``bos``/``choch`` are non-zero at the bar where the break happens and equal
    to the swing price that was broken; ``trend`` is the prevailing HTF trend.
    """
    df = df.copy().reset_index(drop=True)
    df["swing_h"] = np.nan
    df["swing_l"] = np.nan
    df["bos"] = np.nan
    df["choch"] = np.nan
    df["trend"] = Trend.NEUTRAL.value

    sh, sl = find_swings(df, length=length)
    for s in sh:
        df.at[s.index, "swing_h"] = s.price
    for s in sl:
        df.at[s.index, "swing_l"] = s.price

    # Walk the swing sequence alternating highs/lows
    swings: list[SwingPoint] = sorted(sh + sl, key=lambda x: x.index)

    last_h: SwingPoint | None = None
    last_l: SwingPoint | None = None
    trend = Trend.NEUTRAL
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    for i in range(len(df)):
        # did price break above the most recent swing high?
        if last_h is not None and highs[i] > last_h.price:
            if trend == Trend.BULL:
                df.at[i, "bos"] = last_h.price
            else:
                df.at[i, "choch"] = last_h.price
                trend = Trend.BULL
            last_h = None
        if last_l is not None and lows[i] < last_l.price:
            if trend == Trend.BEAR:
                df.at[i, "bos"] = last_l.price
            else:
                df.at[i, "choch"] = last_l.price
                trend = Trend.BEAR
            last_l = None
        # update last swing points seen up to this bar
        for s in swings:
            if s.index == i:
                if s.is_high:
                    last_h = s
                else:
                    last_l = s
        df.at[i, "trend"] = trend.value

    return df
