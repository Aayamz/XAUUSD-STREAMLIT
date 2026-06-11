"""Mock MT5 client.

Simulates a live XAUUSD feed and a broker account so the dashboard, strategy
loop and risk manager can be exercised end-to-end without MetaTrader 5.

The price model is geometric Brownian motion with light mean reversion and
session-aware volatility — good enough to look real on a chart.
"""
from __future__ import annotations

import math
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from utils.config import get_config, get_trading_mode
from utils.logger import get_logger
from utils.time_utils import utc_hour

log = get_logger(__name__)


# --- Timeframe config (seconds per bar) ---------------------------------------
_TF_SECONDS = {
    "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
    "W1": 604800, "MN1": 2592000,
}


def timeframe_to_int(tf: str) -> int:
    return _TF_SECONDS.get(tf.upper(), 3600)


class MockMT5Client:
    name = "mock"

    def __init__(
        self,
        symbol: str = "XAUUSD",
        initial_balance: float = 10_000.0,
        start_price: float = 2350.0,
        spread_points: float = 0.30,
    ):
        self.symbol = symbol
        self.balance = initial_balance
        self.equity = initial_balance
        self.start_price = start_price
        self.last_price = start_price
        self.spread_points = spread_points  # in price units, not points
        self._connected = False
        self.positions: dict[int, dict[str, Any]] = {}
        self.deals: list[dict[str, Any]] = []
        self._bar_cache: dict[tuple[str, int], pd.DataFrame] = {}
        self._rng = np.random.default_rng(seed=int(time.time()) % 100_000)
        self._tick_phase = 0.0

    # --- lifecycle ------------------------------------------------------------
    def connect(self, timeout: int = 10) -> bool:
        time.sleep(0.05)
        self._connected = True
        log.info("[MOCK] Connected — symbol=%s balance=%.2f", self.symbol, self.balance)
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # --- market data ----------------------------------------------------------
    def get_symbol_info(self, symbol: str | None = None) -> dict[str, Any]:
        symbol = symbol or self.symbol
        bid = self._current_bid()
        ask = self._current_ask()
        return {
            "symbol": symbol,
            "digits": 2,
            "point": 0.01,
            "contract_size": 100.0,
            "volume_min": 0.01,
            "volume_max": 100.0,
            "volume_step": 0.01,
            "bid": bid,
            "ask": ask,
            "spread": round(ask - bid, 2),
            "trade_mode": 0,
        }

    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        """Generate a synthetic but deterministic-ish candle history.

        We precompute a long random walk and slice it to the requested count.
        """
        tf = timeframe.upper()
        secs = _TF_SECONDS.get(tf, 3600)
        key = (symbol, secs)
        if key not in self._bar_cache:
            self._bar_cache[key] = self._synth_history(symbol, secs, count=1500)
        df = self._bar_cache[key]
        return df.tail(count).reset_index(drop=True)

    def _synth_history(self, symbol: str, bar_secs: int, count: int) -> pd.DataFrame:
        # Annualised vol ~ 14%, scaled per bar.
        sigma_bar = 0.14 * math.sqrt(bar_secs / (365.0 * 24 * 3600))
        mu = 0.0  # drift
        reversion = 0.0005
        # ~10000 bars worth for "feel" then take last `count`
        n = max(count * 3, 2000)
        rets = self._rng.normal(mu, sigma_bar, size=n)
        # mean reversion to the start price (long-term)
        price = np.empty(n)
        price[0] = self.start_price
        for i in range(1, n):
            price[i] = price[i - 1] * math.exp(rets[i] - reversion * (price[i - 1] / self.start_price - 1))
        # build OHLC
        o = price
        c = np.roll(price, -1)
        c[-1] = price[-1]
        intrabar = np.abs(self._rng.normal(0, sigma_bar, size=n)) * price
        h = np.maximum(o, c) + intrabar * 0.5
        l = np.minimum(o, c) - intrabar * 0.5
        vol = self._rng.integers(800, 6000, size=n)
        spread_pts = self._rng.integers(20, 60, size=n)
        end_ts = int(time.time())
        # align bars to bucket boundaries
        end_ts -= end_ts % bar_secs
        times = [end_ts - (n - 1 - i) * bar_secs for i in range(n)]
        df = pd.DataFrame(
            {
                "time": pd.to_datetime(times, unit="s", utc=True),
                "open": np.round(o, 2),
                "high": np.round(h, 2),
                "low": np.round(l, 2),
                "close": np.round(c, 2),
                "volume": vol,
                "spread_points": spread_pts,
            }
        )
        return df

    # --- account --------------------------------------------------------------
    def get_account_info(self) -> dict[str, Any]:
        # recompute equity = balance + open PnL
        open_pnl = sum(self._position_pnl(p) for p in self.positions.values())
        self.equity = self.balance + open_pnl
        used_margin = sum(self._margin(p) for p in self.positions.values())
        free_margin = max(self.equity - used_margin, 0.0)
        margin_level = (self.equity / used_margin * 100.0) if used_margin > 0 else math.inf
        return {
            "login": 99000001,
            "name": "Mock Account",
            "server": "MOCK-DEMO",
            "currency": "USD",
            "leverage": 100,
            "balance": round(self.balance, 2),
            "equity": round(self.equity, 2),
            "margin": round(used_margin, 2),
            "free_margin": round(free_margin, 2),
            "margin_level": round(margin_level, 2) if math.isfinite(margin_level) else 0.0,
            "profit": round(open_pnl, 2),
        }

    # --- positions / orders ---------------------------------------------------
    def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        self._mark_to_market()
        out = []
        for p in self.positions.values():
            if symbol and p["symbol"] != symbol:
                continue
            out.append(
                {
                    "ticket": p["ticket"],
                    "symbol": p["symbol"],
                    "type": p["type"],
                    "volume": p["volume"],
                    "price_open": p["price_open"],
                    "sl": p["sl"],
                    "tp": p["tp"],
                    "price_current": self._current_bid() if p["type"] == "BUY" else self._current_ask(),
                    "profit": round(self._position_pnl(p), 2),
                    "swap": 0.0,
                    "magic": p["magic"],
                    "comment": p["comment"],
                    "time": p["time"],
                }
            )
        return out

    def place_order(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        sl: float | None = None,
        tp: float | None = None,
        comment: str = "",
        magic: int = 0,
    ) -> dict[str, Any]:
        ot = order_type.upper()
        if ot not in {"BUY", "SELL"}:
            return {"retcode": 10013, "ok": False, "comment": f"unsupported {ot}"}
        # tiny slippage
        slip = self._rng.normal(0, 0.05)
        price = (self._current_ask() if ot == "BUY" else self._current_bid()) + slip
        ticket = int(time.time() * 1000) ^ random.randint(0, 9999)
        pos = {
            "ticket": ticket,
            "symbol": symbol,
            "type": ot,
            "volume": round(float(volume), 2),
            "price_open": round(price, 2),
            "sl": sl,
            "tp": tp,
            "magic": magic,
            "comment": comment,
            "time": int(time.time()),
        }
        self.positions[ticket] = pos
        log.info("[MOCK] OPEN %s %.2f @ %.2f sl=%s tp=%s", ot, volume, price, sl, tp)
        return {
            "retcode": 10009,  # TRADE_RETCODE_DONE
            "ticket": ticket,
            "price": round(price, 2),
            "volume": pos["volume"],
            "comment": "mock fill",
            "ok": True,
        }

    def close_position(self, ticket: int) -> bool:
        p = self.positions.get(ticket)
        if not p:
            return False
        pnl = self._position_pnl(p)
        self.balance += pnl
        deal = {
            "ticket": p["ticket"],
            "deal": int(uuid.uuid4().int % 1_000_000),
            "symbol": p["symbol"],
            "type": 1 if p["type"] == "BUY" else 0,
            "entry": 1,
            "volume": p["volume"],
            "price": self._current_bid() if p["type"] == "BUY" else self._current_ask(),
            "profit": round(pnl, 2),
            "swap": 0.0,
            "commission": 0.0,
            "time": int(time.time()),
            "comment": "mock close",
        }
        self.deals.append(deal)
        log.info("[MOCK] CLOSE ticket=%s pnl=%.2f", ticket, pnl)
        del self.positions[ticket]
        return True

    def partial_close_position(self, ticket: int, volume: float) -> bool:
        p = self.positions.get(ticket)
        if not p:
            return False
        if volume >= p["volume"]:
            return self.close_position(ticket)
        # Partial close: reduce volume and record partial PnL
        close_price = self._current_bid() if p["type"] == "BUY" else self._current_ask()
        contract = 100.0
        if p["type"] == "BUY":
            pnl = (close_price - p["price_open"]) * volume * contract
        else:
            pnl = (p["price_open"] - close_price) * volume * contract
        self.balance += pnl
        p["volume"] = round(p["volume"] - volume, 2)
        deal = {
            "ticket": p["ticket"],
            "deal": int(uuid.uuid4().int % 1_000_000),
            "symbol": p["symbol"],
            "type": 1 if p["type"] == "BUY" else 0,
            "entry": 1,
            "volume": volume,
            "price": close_price,
            "profit": round(pnl, 2),
            "swap": 0.0,
            "commission": 0.0,
            "time": int(time.time()),
            "comment": "mock partial close",
        }
        self.deals.append(deal)
        log.info("[MOCK] PARTIAL CLOSE ticket=%s vol=%.2f pnl=%.2f", ticket, volume, pnl)
        return True

    def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> bool:
        p = self.positions.get(ticket)
        if not p:
            return False
        if sl is not None:
            p["sl"] = float(sl)
        if tp is not None:
            p["tp"] = float(tp)
        return True

    def get_history_deals(self, days: int = 30) -> list[dict[str, Any]]:
        return list(self.deals)

    # --- internals ------------------------------------------------------------
    def _session_vol_mult(self) -> float:
        h = utc_hour()
        # London / NY overlap 12-16 UTC: 1.2x; off-hours: 0.6x
        if 12 <= h < 16:
            return 1.2
        if 7 <= h < 16 or 13 <= h < 21:
            return 1.0
        return 0.6

    def _current_bid(self) -> float:
        self._tick_phase += 0.0002 * self._session_vol_mult()
        self.last_price = self.start_price * (1.0 + 0.02 * math.sin(self._tick_phase / 5.0)) \
            + self._rng.normal(0, 0.4 * self._session_vol_mult())
        return round(self.last_price - self.spread_points / 2, 2)

    def _current_ask(self) -> float:
        return round(self._current_bid() + self.spread_points, 2)

    def _position_pnl(self, p: dict[str, Any]) -> float:
        contract = 100.0  # XAUUSD contract size
        if p["type"] == "BUY":
            cur = self._current_bid()
        else:
            cur = self._current_ask()
        return (cur - p["price_open"]) * p["volume"] * contract

    def _margin(self, p: dict[str, Any]) -> float:
        contract = 100.0
        leverage = 100
        notional = p["price_open"] * p["volume"] * contract
        return notional / leverage

    def _mark_to_market(self) -> None:
        """Touch the price feed so PnL evolves between calls."""
        _ = self._current_bid()
