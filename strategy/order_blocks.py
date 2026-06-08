"""Order Block detection (LuxAlgo inspired).

Bullish OB = last bearish candle before a strong bullish move that broke the
previous swing high. Bearish OB is the mirror.

We then mark the OB as ``mitigated`` when price later trades through its
boundary (entry signal) and ``invaliated`` when price closes beyond the OB's
opposite end.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd

from .structure import find_swings, label_structure


@dataclass
class OrderBlock:
    index: int             # bar where the OB originates
    top: float             # high
    bottom: float          # low
    is_bullish: bool
    mitigated: bool = False
    invalidated: bool = False
    bias: str = ""         # BOS/CHOCH string captured at creation
    bars_since: int = 0    # how many bars ago the OB was formed (recency)
    distance_to_close: float = 0.0  # signed distance from last close to OB mid (negative=below for bullish)


def find_order_blocks(
    df: pd.DataFrame,
    swing_length: int = 5,
    min_displacement_atr: float = 1.5,
    lookback: int = 50,
) -> List[OrderBlock]:
    """Return active order blocks in the most recent ``lookback`` bars."""
    if len(df) < swing_length * 2 + 5:
        return []

    atr = (df["high"] - df["low"]).rolling(14).mean()
    df_s = label_structure(df, length=swing_length)

    blocks: List[OrderBlock] = []

    for i in range(swing_length, len(df)):
        bos = df_s["bos"].iloc[i]
        choch = df_s["choch"].iloc[i]
        if np.isnan(bos) and np.isnan(choch):
            continue
        if pd.isna(atr.iloc[i]) or atr.iloc[i] == 0:
            continue

        # find the OB: walk back from bar i to find the last opposite-colour
        # candle prior to the displacement.
        is_bull_break = not np.isnan(bos) and df_s["close"].iloc[i] > df_s["open"].iloc[i]
        is_bear_break = not np.isnan(bos) and df_s["close"].iloc[i] < df_s["open"].iloc[i]

        if is_bull_break:
            for j in range(i - 1, max(i - 20, swing_length), -1):
                if df_s["close"].iloc[j] < df_s["open"].iloc[j]:
                    body = abs(df_s["close"].iloc[j] - df_s["open"].iloc[j])
                    if body >= atr.iloc[i] * 0.1:  # body not tiny
                        ob = OrderBlock(
                            index=j,
                            top=float(df_s["high"].iloc[j]),
                            bottom=float(df_s["low"].iloc[j]),
                            is_bullish=True,
                            bias="BOS",
                        )
                        blocks.append(ob)
                        break
        elif is_bear_break:
            for j in range(i - 1, max(i - 20, swing_length), -1):
                if df_s["close"].iloc[j] > df_s["open"].iloc[j]:
                    body = abs(df_s["close"].iloc[j] - df_s["open"].iloc[j])
                    if body >= atr.iloc[i] * 0.1:
                        ob = OrderBlock(
                            index=j,
                            top=float(df_s["high"].iloc[j]),
                            bottom=float(df_s["low"].iloc[j]),
                            is_bullish=False,
                            bias="BOS",
                        )
                        blocks.append(ob)
                        break

    # Also append CHoCH-origin OBs (reversal zones)
    for i in range(swing_length, len(df)):
        choch = df_s["choch"].iloc[i]
        if np.isnan(choch):
            continue
        bullish_choch = df_s["close"].iloc[i] > df_s["open"].iloc[i]
        for j in range(i - 1, max(i - 20, swing_length), -1):
            if bullish_choch and df_s["close"].iloc[j] < df_s["open"].iloc[j]:
                ob = OrderBlock(
                    index=j,
                    top=float(df_s["high"].iloc[j]),
                    bottom=float(df_s["low"].iloc[j]),
                    is_bullish=True,
                    bias="CHoCH",
                )
                blocks.append(ob)
                break
            if (not bullish_choch) and df_s["close"].iloc[j] > df_s["open"].iloc[j]:
                ob = OrderBlock(
                    index=j,
                    top=float(df_s["high"].iloc[j]),
                    bottom=float(df_s["low"].iloc[j]),
                    is_bullish=False,
                    bias="CHoCH",
                )
                blocks.append(ob)
                break

    # dedupe by (index, is_bullish)
    seen = set()
    unique: List[OrderBlock] = []
    for b in blocks:
        k = (b.index, b.is_bullish)
        if k in seen:
            continue
        seen.add(k)
        unique.append(b)

    # mark mitigated / invalidated using the bars after the OB
    last_close = float(df["close"].iloc[-1])
    if unique:
        for b in unique:
            sub = df.iloc[b.index + 1 :]
            if b.is_bullish:
                # Mitigated = a single bar's low traded INTO the OB range
                if ((sub["low"] <= b.top) & (sub["low"] >= b.bottom)).any():
                    b.mitigated = True
                if (sub["close"] < b.bottom).any():
                    b.invalidated = True
            else:
                # Mitigated = a single bar's high traded INTO the OB range
                if ((sub["high"] >= b.bottom) & (sub["high"] <= b.top)).any():
                    b.mitigated = True
                if (sub["close"] > b.top).any():
                    b.invalidated = True
            b.bars_since = len(df) - 1 - b.index
            mid = (b.top + b.bottom) / 2.0
            b.distance_to_close = last_close - mid

    # keep only the most recent ``lookback`` and active (not invalidated) ones
    unique = [b for b in unique if not b.invalidated and b.index >= len(df) - lookback]
    # sort: most recent first, but kept stable
    unique.sort(key=lambda b: b.index, reverse=True)
    return unique
