"""Real MetaTrader 5 client.

All public methods are deliberately thin wrappers — they translate between
pandas / dict and MT5's C-style structs, and surface errors as ``RuntimeError``
so the caller can log/notify uniformly.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
    _MT5_OK = True
except Exception:  # pragma: no cover - import-time guard
    mt5 = None  # type: ignore
    _MT5_OK = False

from utils.logger import get_logger

log = get_logger(__name__)


# --- Timeframe mapping ---------------------------------------------------------
_TIMEFRAMES: dict[str, int] = {
    "M1": getattr(mt5, "TIMEFRAME_M1", 1) if _MT5_OK else 1,
    "M5": getattr(mt5, "TIMEFRAME_M5", 5) if _MT5_OK else 5,
    "M15": getattr(mt5, "TIMEFRAME_M15", 15) if _MT5_OK else 15,
    "M30": getattr(mt5, "TIMEFRAME_M30", 30) if _MT5_OK else 30,
    "H1": getattr(mt5, "TIMEFRAME_H1", 16385) if _MT5_OK else 16385,
    "H4": getattr(mt5, "TIMEFRAME_H4", 16388) if _MT5_OK else 16388,
    "D1": getattr(mt5, "TIMEFRAME_D1", 16408) if _MT5_OK else 16408,
    "W1": getattr(mt5, "TIMEFRAME_W1", 32769) if _MT5_OK else 32769,
    "MN1": getattr(mt5, "TIMEFRAME_MN1", 49153) if _MT5_OK else 49153,
}


def timeframe_to_int(tf: str) -> int:
    return _TIMEFRAMES.get(tf.upper(), _TIMEFRAMES["H1"])


def timeframe_to_seconds(tf: str) -> int:
    return {
        "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
        "H1": 3600, "H4": 14400, "D1": 86400,
        "W1": 604800, "MN1": 2592000,
    }.get(tf.upper(), 3600)


# --- Order type mapping --------------------------------------------------------
def _order_type_map() -> dict[str, int]:
    if not _MT5_OK:
        return {}
    return {
        "BUY": mt5.ORDER_TYPE_BUY,
        "SELL": mt5.ORDER_TYPE_SELL,
        "BUY_LIMIT": mt5.ORDER_TYPE_BUY_LIMIT,
        "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
        "BUY_STOP": mt5.ORDER_TYPE_BUY_STOP,
        "SELL_STOP": mt5.ORDER_TYPE_SELL_STOP,
    }


class RealMT5Client:
    name = "real"

    def __init__(self, login: int, password: str, server: str, path: str = ""):
        self.login = int(login)
        self.password = password
        self.server = server
        self.path = path
        self._connected = False

    # --- lifecycle ------------------------------------------------------------
    def connect(self, timeout: int = 10) -> bool:
        if not _MT5_OK:
            raise RuntimeError("MetaTrader5 package not available")
        init_kwargs: dict[str, Any] = {"timeout": timeout * 1000}
        if self.path:
            init_kwargs["path"] = self.path
        if not mt5.initialize(**init_kwargs):
            err = mt5.last_error()
            raise RuntimeError(f"MT5 initialize failed: {err}")
        authorized = mt5.login(
            login=self.login, password=self.password, server=self.server, timeout=timeout * 1000
        )
        if not authorized:
            err = mt5.last_error()
            mt5.shutdown()
            raise RuntimeError(f"MT5 login failed: {err}")
        self._connected = True
        log.info("Connected to MT5 account %s @ %s", self.login, self.server)
        return True

    def disconnect(self) -> None:
        if _MT5_OK and self._connected:
            mt5.shutdown()
        self._connected = False

    def is_connected(self) -> bool:
        if not _MT5_OK or not self._connected:
            return False
        term = mt5.terminal_info()
        return bool(term and term.connected)

    # --- market data ----------------------------------------------------------
    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        self._ensure()
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Symbol {symbol} not found")
        tick = mt5.symbol_info_tick(symbol)
        return {
            "symbol": info.name,
            "digits": info.digits,
            "point": info.point,
            "contract_size": info.trade_contract_size,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
            "bid": tick.bid if tick else info.bid,
            "ask": tick.ask if tick else info.ask,
            "spread": (tick.ask - tick.bid) if tick else info.spread,
            "trade_mode": info.trade_mode,
            "trade_stops_level": getattr(info, "trade_stops_level", 0) or 0,
            "trade_freeze_level": getattr(info, "trade_freeze_level", 0) or 0,
        }

    def get_ohlcv(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        self._ensure()
        rates = mt5.copy_rates_from_pos(symbol, timeframe_to_int(timeframe), 0, count)
        if rates is None or len(rates) == 0:
            err = mt5.last_error()
            raise RuntimeError(f"copy_rates_from_pos failed: {err}")
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.rename(
            columns={"tick_volume": "volume", "spread": "spread_points"},
            inplace=True,
        )
        return df[["time", "open", "high", "low", "close", "volume", "spread_points"]]

    # --- account --------------------------------------------------------------
    def get_account_info(self) -> dict[str, Any]:
        self._ensure()
        a = mt5.account_info()
        if a is None:
            raise RuntimeError("account_info() returned None")
        return {
            "login": a.login,
            "name": a.name,
            "server": a.server,
            "currency": a.currency,
            "leverage": a.leverage,
            "balance": a.balance,
            "equity": a.equity,
            "margin": a.margin,
            "free_margin": a.margin_free,
            "margin_level": a.margin_level,
            "profit": a.profit,
        }

    # --- positions / orders ---------------------------------------------------
    def get_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        self._ensure()
        req: dict[str, Any] = {}
        if symbol:
            req["symbol"] = symbol
        pos = mt5.positions_get(**req) if req else mt5.positions_get()
        if pos is None:
            return []
        out = []
        for p in pos:
            out.append(
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "sl": p.sl,
                    "tp": p.tp,
                    "price_current": p.price_current,
                    "profit": p.profit,
                    "swap": p.swap,
                    "magic": p.magic,
                    "comment": p.comment,
                    "time": p.time,
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
        self._ensure()
        sym = mt5.symbol_info(symbol)
        if sym is None:
            raise RuntimeError(f"Symbol {symbol} not found")
        tick = mt5.symbol_info_tick(symbol)
        ot = _order_type_map()[order_type.upper()]
        price = tick.ask if ot == mt5.ORDER_TYPE_BUY else tick.bid

        # --- Enforce broker minimum stop distance (trade_stops_level) ----------
        # MT5 retcode 10016 "Invalid stops" is raised when SL/TP sit closer to
        # the requested price than the broker's allowed minimum. We expand them
        # outward so the order is accepted.
        point = float(sym.point or 0.01)
        digits = int(sym.digits or 2)
        stops_level = int(getattr(sym, "trade_stops_level", 0) or 0)
        min_distance = stops_level * point

        # --- Validate SL/TP are on the correct side of price --------------------
        # For BUY:  SL < price < TP
        # For SELL: TP < price < SL
        if ot == mt5.ORDER_TYPE_BUY:
            if sl is not None and sl >= price:
                log.warning("BUY SL %.2f >= price %.2f — clearing SL", sl, price)
                sl = None
            if tp is not None and tp <= price:
                log.warning("BUY TP %.2f <= price %.2f — clearing TP", tp, price)
                tp = None
            if sl is not None and min_distance > 0 and price - sl < min_distance:
                sl = round(price - min_distance, digits)
                log.info("BUY SL too close — adjusted to %.2f", sl)
            if tp is not None and min_distance > 0 and tp - price < min_distance:
                tp = round(price + min_distance, digits)
                log.info("BUY TP too close — adjusted to %.2f", tp)
        else:  # SELL
            if sl is not None and sl <= price:
                log.warning("SELL SL %.2f <= price %.2f — clearing SL", sl, price)
                sl = None
            if tp is not None and tp >= price:
                log.warning("SELL TP %.2f >= price %.2f — clearing TP", tp, price)
                tp = None
            if sl is not None and min_distance > 0 and sl - price < min_distance:
                sl = round(price + min_distance, digits)
                log.info("SELL SL too close — adjusted to %.2f", sl)
            if tp is not None and min_distance > 0 and price - tp < min_distance:
                tp = round(price - min_distance, digits)
                log.info("SELL TP too close — adjusted to %.2f", tp)

        # --- Round volume to broker's volume_step and clamp to [min, max] ------
        step = float(sym.volume_step or 0.01)
        vmin = float(sym.volume_min or step)
        vmax = float(sym.volume_max or 100.0)
        volume = max(vmin, min(volume, vmax))
        volume = round(volume / step) * step
        volume = round(volume, 4)

        req: dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": ot,
            "price": price,
            "deviation": 20,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl:
            req["sl"] = float(sl)
        if tp:
            req["tp"] = float(tp)
        result = mt5.order_send(req)
        if result is None:
            raise RuntimeError("order_send returned None")
        return {
            "retcode": result.retcode,
            "ticket": result.order,
            "price": result.price,
            "volume": result.volume,
            "comment": result.comment,
            "ok": result.retcode == mt5.TRADE_RETCODE_DONE,
            "submitted_volume": volume,
            "sl_adjusted": sl,
            "tp_adjusted": tp,
        }

    def close_position(self, ticket: int) -> bool:
        self._ensure()
        pos_list = mt5.positions_get(ticket=ticket)
        if not pos_list:
            return False
        p = pos_list[0]
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None:
            return False
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": p.magic,
            "comment": "close_by_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        r = mt5.order_send(req)
        return bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)

    def partial_close_position(self, ticket: int, volume: float) -> bool:
        """Close a partial volume of an open position."""
        self._ensure()
        pos_list = mt5.positions_get(ticket=ticket)
        if not pos_list:
            return False
        p = pos_list[0]
        if volume >= p.volume:
            return self.close_position(ticket)
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None:
            return False
        close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": float(volume),
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": p.magic,
            "comment": "partial_close_by_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        r = mt5.order_send(req)
        return bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)

    def modify_position(self, ticket: int, sl: float | None = None, tp: float | None = None) -> bool:
        self._ensure()
        req: dict[str, Any] = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket}
        if sl is not None:
            req["sl"] = float(sl)
        if tp is not None:
            req["tp"] = float(tp)
        r = mt5.order_send(req)
        return bool(r and r.retcode == mt5.TRADE_RETCODE_DONE)

    def get_history_deals(self, days: int = 30) -> list[dict[str, Any]]:
        self._ensure()
        date_from = datetime.now(tz=timezone.utc) - timedelta(days=days)
        date_to = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        deals = mt5.history_deals_get(date_from, date_to)
        if deals is None:
            return []
        out = []
        for d in deals:
            out.append(
                {
                    "ticket": d.order,
                    "deal": d.ticket,
                    "symbol": d.symbol,
                    "type": d.type,
                    "entry": d.entry,
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "swap": d.swap,
                    "commission": d.commission,
                    "time": d.time,
                    "comment": d.comment,
                }
            )
        return out

    # --- internals ------------------------------------------------------------
    def _ensure(self) -> None:
        if not _MT5_OK:
            raise RuntimeError("MetaTrader5 package not available")
        if not self.is_connected():
            self.connect()
