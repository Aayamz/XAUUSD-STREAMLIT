"""Indicator helpers — uses pandas_ta when available, falls back to pandas.

We always work on a DataFrame indexed by integer position; ``time`` is kept as a
column for plotting but ignored for math.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import pandas_ta as pta
    _PTA = True
except Exception:  # pragma: no cover
    pta = None
    _PTA = False


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    if _PTA:
        s = pta.atr(df["high"], df["low"], df["close"], length=length)
        if s is not None:
            return s.bfill()
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    if _PTA:
        s = pta.ema(series, length=length)
        if s is not None:
            return s
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    if _PTA:
        s = pta.rsi(series, length=length)
        if s is not None:
            return s
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Mutates and returns df with a standard indicator suite."""
    df = df.copy()
    df["atr14"] = atr(df, 14)
    df["atr50"] = atr(df, 50)
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi14"] = rsi(df["close"], 14)
    return df
