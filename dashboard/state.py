"""Shared dashboard state — one MT5 client per Streamlit session.

Streamlit reruns the script on every interaction, so we cache the client (and
the data fetcher / strategy) via ``st.cache_resource`` to avoid reconnecting
or recomputing heavy objects on every rerun.

Also exposes a ``BotRunner`` singleton that runs the trading loop in a
background thread, started/stopped from the dashboard's auto-trading toggle.
"""
from __future__ import annotations

import threading
from typing import Any

import pandas as pd
import streamlit as st

from data.fetcher import DataFetcher
from mt5_connector.factory import build_client
from strategy import create_strategy, list_strategies, available_strategies_for_mode
from utils.config import get_config
from utils.logger import get_logger

log = get_logger(__name__)


# --- MT5 client & data fetchers ------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_client() -> Any:
    return build_client()


@st.cache_resource(show_spinner=False)
def get_fetcher(_client: Any) -> DataFetcher:
    return DataFetcher(_client)


@st.cache_resource(show_spinner=False)
def get_strategy(mode: str = "swing", strategy_name: str | None = None) -> Any:
    cfg = get_config().get("strategy", {})
    name = strategy_name or cfg.get("active_strategy", "luxalgo_smc")
    # Fall back to luxalgo_smc if the requested strategy isn't registered
    try:
        return create_strategy(name, cfg=cfg, mode=mode)
    except ValueError:
        log.warning("Strategy %s not found, falling back to luxalgo_smc", name)
        return create_strategy("luxalgo_smc", cfg=cfg, mode=mode)


# --- Control bus (manual trade commands from the dashboard) ------------------
class ControlBus:
    """Process-local bus for manual trade commands from the dashboard."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.commands: list[dict[str, Any]] = []
        self.kill_switch: bool = False
        self.last_signal: dict[str, Any] | None = None

    def push(self, cmd: dict[str, Any]) -> None:
        with self._lock:
            self.commands.append(cmd)

    def drain(self) -> list[dict[str, Any]]:
        with self._lock:
            cmds = self.commands[:]
            self.commands.clear()
            return cmds

    def toggle_kill(self, value: bool | None = None) -> bool:
        with self._lock:
            if value is not None:
                self.kill_switch = value
            else:
                self.kill_switch = not self.kill_switch
            return self.kill_switch

    def update_signal(self, signal_data: dict[str, Any]) -> None:
        with self._lock:
            self.last_signal = signal_data

    def get_last_signal(self) -> dict[str, Any] | None:
        with self._lock:
            return self.last_signal


@st.cache_resource(show_spinner=False)
def get_control_bus() -> ControlBus:
    return ControlBus()


# --- Auto-trading runner (background thread) ---------------------------------
class BotRunner:
    """Run the trading loop in a background thread.

    The toggle in the dashboard sidebar calls ``start()`` / ``stop()`` to
    control this. The thread survives Streamlit reruns because the instance
    is cached with ``st.cache_resource``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bot = None
        self._scheduler = None
        self._running = False
        self._interval = 60
        self._last_tick_ts: float = 0.0
        self._last_error: str | None = None
        self._ticks_run: int = 0
        self._trades_opened: int = 0

    def start(self, interval: int | None = None) -> bool:
        """Start the background loop. Returns True if state changed."""
        with self._lock:
            if self._running:
                if interval and interval != self._interval:
                    self._set_interval_locked(interval)
                return False
            try:
                from apscheduler.schedulers.background import BackgroundScheduler
            except ImportError:
                log.error("APScheduler not installed")
                self._last_error = "APScheduler not installed"
                return False

            try:
                from bot import TradingBot
                self._bot = TradingBot()
            except Exception as e:  # noqa: BLE001
                log.error("Failed to construct TradingBot: %s", e)
                self._last_error = f"Bot init failed: {e}"
                return False

            self._interval = interval or self._interval
            self._scheduler = BackgroundScheduler(timezone="UTC")
            self._scheduler.add_job(
                self._safe_tick, "interval", seconds=self._interval,
                id="strategy", max_instances=1, coalesce=True,
            )
            self._scheduler.start()
            self._running = True
            self._last_error = None
            log.info("Auto-trading started (interval=%ss, symbol=%s)",
                     self._interval, self._bot.symbol)
            return True

    def stop(self) -> bool:
        with self._lock:
            if not self._running:
                return False
            try:
                if self._scheduler:
                    self._scheduler.shutdown(wait=False)
            except Exception as e:  # noqa: BLE001
                log.warning("Scheduler shutdown error: %s", e)
            self._scheduler = None
            self._running = False
            log.info("Auto-trading stopped")
            return True

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def set_interval(self, seconds: int) -> None:
        with self._lock:
            self._set_interval_locked(seconds)

    def _set_interval_locked(self, seconds: int) -> None:
        if not self._running or not self._scheduler:
            self._interval = seconds
            return
        try:
            self._scheduler.reschedule_job(
                "strategy", trigger="interval", seconds=seconds,
            )
            self._interval = seconds
            log.info("Rescheduled auto-trading to every %ss", seconds)
        except Exception as e:  # noqa: BLE001
            log.error("Failed to reschedule: %s", e)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._running,
                "interval": self._interval,
                "symbol": self._bot.symbol if self._bot else None,
                "mode": self._bot.strategy.mode if self._bot else None,
                "last_tick_ts": self._last_tick_ts,
                "last_error": self._last_error,
                "ticks_run": self._ticks_run,
                "trades_opened": self._trades_opened,
            }

    def record_trade_opened(self) -> None:
        with self._lock:
            self._trades_opened += 1

    def _safe_tick(self) -> None:
        import time
        if self._bot is None:
            return
        try:
            self._bot.tick()
            with self._lock:
                self._last_tick_ts = time.time()
                self._ticks_run += 1
                self._last_error = None
        except Exception as e:  # noqa: BLE001
            log.error("Tick error: %s", e)
            with self._lock:
                self._last_error = str(e)


@st.cache_resource(show_spinner=False)
def get_bot_runner() -> BotRunner:
    return BotRunner()


# --- Convenience wrappers ----------------------------------------------------
def fetch_bars(symbol: str, timeframe: str, count: int) -> pd.DataFrame:
    return get_fetcher(get_client()).get_bars(symbol, timeframe, count)


def fetch_account() -> dict[str, Any]:
    return get_client().get_account_info()


def fetch_positions(symbol: str | None = None) -> list[dict[str, Any]]:
    return get_client().get_positions(symbol=symbol)


def fetch_history(days: int = 30) -> list[dict[str, Any]]:
    return get_client().get_history_deals(days=days)


def fetch_symbol_info(symbol: str) -> dict[str, Any]:
    return get_client().get_symbol_info(symbol)
