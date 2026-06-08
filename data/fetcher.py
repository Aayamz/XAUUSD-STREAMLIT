"""Thin wrapper over the MT5 client that adds caching and convenience."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd

from utils.config import PROJECT_ROOT
from utils.logger import get_logger

log = get_logger(__name__)

CACHE_DIR = PROJECT_ROOT / "data_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL_SECONDS = 30  # how long a bar snapshot is considered fresh


def _cache_path(symbol: str, tf: str, count: int) -> Path:
    safe = symbol.replace("/", "_")
    return CACHE_DIR / f"{safe}_{tf.upper()}_{count}.parquet"


class DataFetcher:
    def __init__(self, client: Any):
        self.client = client

    def get_bars(self, symbol: str, timeframe: str, count: int, use_cache: bool = True) -> pd.DataFrame:
        cache = _cache_path(symbol, timeframe, count)
        if use_cache and cache.exists() and (time.time() - cache.stat().st_mtime) < CACHE_TTL_SECONDS:
            try:
                return pd.read_parquet(cache)
            except Exception:  # noqa: BLE001
                pass
        df = self.client.get_ohlcv(symbol, timeframe, count)
        if df is None or df.empty:
            return df
        try:
            df.to_parquet(cache, index=False)
        except Exception:  # noqa: BLE001
            pass
        return df

    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        return self.client.get_symbol_info(symbol)

    def get_account_info(self) -> dict[str, Any]:
        return self.client.get_account_info()

    def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return self.client.get_positions(symbol=symbol)

    def get_history_deals(self, days: int = 30) -> list[dict[str, Any]]:
        return self.client.get_history_deals(days=days)
