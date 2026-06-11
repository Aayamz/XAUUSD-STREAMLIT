"""Config loading and path helpers.

We load YAML once at import time and cache it. The dashboard also uses this so
all modules share the same configuration source.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

# Load .env if present (silently ignored otherwise)
load_dotenv(ENV_PATH, override=False)


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and sanitize configuration parameters."""
    validated = config.copy()

    # Validate app section
    if "app" not in validated:
        validated["app"] = {}
    app_cfg = validated["app"]
    app_cfg.setdefault("symbol", "XAUUSD")
    app_cfg.setdefault("log_level", "INFO")
    refresh_sec = app_cfg.get("refresh_seconds", 60)
    app_cfg["refresh_seconds"] = max(10, min(int(refresh_sec), 300))  # 10s to 5min

    # Validate mt5 section
    if "mt5" not in validated:
        validated["mt5"] = {}
    mt5_cfg = validated["mt5"]
    mt5_cfg.setdefault("timeout_seconds", 10)
    mt5_cfg.setdefault("max_reconnect_attempts", 5)
    mt5_cfg.setdefault("reconnect_backoff_seconds", 5)
    mt5_cfg["timeout_seconds"] = max(5, min(int(mt5_cfg["timeout_seconds"]), 30))
    mt5_cfg["max_reconnect_attempts"] = max(0, min(int(mt5_cfg["max_reconnect_attempts"]), 10))
    mt5_cfg["reconnect_backoff_seconds"] = max(1, min(int(mt5_cfg["reconnect_backoff_seconds"]), 10))

    # Validate dashboard section
    if "dashboard" not in validated:
        validated["dashboard"] = {}
    dash_cfg = validated["dashboard"]
    dash_cfg.setdefault("theme", "dark")
    dash_cfg.setdefault("default_timeframe", "H1")
    dash_cfg.setdefault("chart_lookback_bars", 200)
    lookback = dash_cfg.get("chart_lookback_bars", 200)
    dash_cfg["chart_lookback_bars"] = max(50, min(int(lookback), 2000))

    # Validate strategy section
    if "strategy" not in validated:
        validated["strategy"] = {}
    strat_cfg = validated["strategy"]
    strat_cfg.setdefault("enabled", True)
    strat_cfg.setdefault("name", "LuxAlgo SMC")
    strat_cfg.setdefault("active_strategy", "luxalgo_smc")
    strat_cfg.setdefault("higher_timeframe", "H4")
    strat_cfg.setdefault("entry_timeframe", "M15")
    strat_cfg.setdefault("scalp_higher_timeframe", "M15")
    strat_cfg.setdefault("scalp_entry_timeframe", "M5")
    strat_cfg.setdefault("mode", "swing")
    strat_cfg.setdefault("ignore_session_filter", False)
    strat_cfg.setdefault("swing_length", 3)
    strat_cfg.setdefault("ob_lookback", 200)
    strat_cfg.setdefault("ob_min_displacement_atr", 0.5)
    strat_cfg.setdefault("ob_proximity_atr", 1.5)
    strat_cfg.setdefault("fvg_min_size_atr", 0.2)
    strat_cfg.setdefault("liquidity_lookback", 100)
    strat_cfg.setdefault("liquidity_tolerance_atr", 0.5)
    strat_cfg.setdefault("min_rr", 2.0)
    strat_cfg.setdefault("scalp_min_rr", 1.0)
    strat_cfg.setdefault("confidence_threshold", 55)
    strat_cfg.setdefault("scalp_confidence_threshold", 50)

    # Validate numeric strategy parameters
    swing_len = strat_cfg.get("swing_length", 3)
    strat_cfg["swing_length"] = max(1, min(int(swing_len), 20))

    ob_lookback = strat_cfg.get("ob_lookback", 200)
    strat_cfg["ob_lookback"] = max(10, min(int(ob_lookback), 500))

    ob_min_disp = strat_cfg.get("ob_min_displacement_atr", 0.5)
    strat_cfg["ob_min_displacement_atr"] = max(0.1, min(float(ob_min_disp), 5.0))

    ob_prox = strat_cfg.get("ob_proximity_atr", 1.5)
    strat_cfg["ob_proximity_atr"] = max(0.1, min(float(ob_prox), 5.0))

    fvg_min = strat_cfg.get("fvg_min_size_atr", 0.2)
    strat_cfg["fvg_min_size_atr"] = max(0.05, min(float(fvg_min), 2.0))

    liq_lookback = strat_cfg.get("liquidity_lookback", 100)
    strat_cfg["liquidity_lookback"] = max(10, min(int(liq_lookback), 500))

    liq_tol = strat_cfg.get("liquidity_tolerance_atr", 0.5)
    strat_cfg["liquidity_tolerance_atr"] = max(0.1, min(float(liq_tol), 2.0))

    min_rr = strat_cfg.get("min_rr", 2.0)
    strat_cfg["min_rr"] = max(0.5, min(float(min_rr), 10.0))

    scalp_min_rr = strat_cfg.get("scalp_min_rr", 1.0)
    strat_cfg["scalp_min_rr"] = max(0.5, min(float(scalp_min_rr), 5.0))

    conf_thresh = strat_cfg.get("confidence_threshold", 55)
    strat_cfg["confidence_threshold"] = max(1, min(int(conf_thresh), 99))

    scalp_conf_thresh = strat_cfg.get("scalp_confidence_threshold", 50)
    strat_cfg["scalp_confidence_threshold"] = max(1, min(int(scalp_conf_thresh), 99))

    # Validate sessions
    if "sessions" not in strat_cfg:
        strat_cfg["sessions"] = {}
    sessions = strat_cfg["sessions"]
    sessions.setdefault("london", {"start": 7, "end": 16, "enabled": True})
    sessions.setdefault("new_york", {"start": 12, "end": 21, "enabled": True})
    sessions.setdefault("asia", {"start": 0, "end": 8, "enabled": False})

    for sess_name, sess_cfg in sessions.items():
        if isinstance(sess_cfg, dict):
            sess_cfg.setdefault("enabled", True)
            sess_cfg.setdefault("start", 0)
            sess_cfg.setdefault("end", 23)
            start = max(0, min(int(sess_cfg.get("start", 0)), 23))
            end = max(0, min(int(sess_cfg.get("end", 23)), 23))
            sess_cfg["start"] = start
            sess_cfg["end"] = end

    # Validate risk section
    if "risk" not in validated:
        validated["risk"] = {}
    risk_cfg = validated["risk"]
    risk_cfg.setdefault("account_risk_pct", 0.5)
    risk_cfg.setdefault("daily_loss_limit_pct", 4.0)
    risk_cfg.setdefault("max_drawdown_pct", 12.0)
    risk_cfg.setdefault("max_concurrent_positions", 1)
    risk_cfg.setdefault("default_lot_size", 0.01)
    risk_cfg.setdefault("max_lot_size", 0.10)
    risk_cfg.setdefault("use_trailing_stop", True)
    risk_cfg.setdefault("trailing_stop_atr_mult", 1.5)
    risk_cfg.setdefault("trailing_start_rr", 1.0)
    risk_cfg.setdefault("break_even_after_rr", 1.0)
    risk_cfg.setdefault("use_partial_take_profit", True)
    risk_cfg.setdefault("partial_tp_rr", 1.0)

    # Validate numeric risk parameters
    account_risk = risk_cfg.get("account_risk_pct", 0.5)
    risk_cfg["account_risk_pct"] = max(0.01, min(float(account_risk), 5.0))

    daily_loss = risk_cfg.get("daily_loss_limit_pct", 4.0)
    risk_cfg["daily_loss_limit_pct"] = max(0.1, min(float(daily_loss), 20.0))

    max_dd = risk_cfg.get("max_drawdown_pct", 12.0)
    risk_cfg["max_drawdown_pct"] = max(0.1, min(float(max_dd), 50.0))

    max_pos = risk_cfg.get("max_concurrent_positions", 1)
    risk_cfg["max_concurrent_positions"] = max(1, min(int(max_pos), 10))

    default_lot = risk_cfg.get("default_lot_size", 0.01)
    risk_cfg["default_lot_size"] = max(0.001, min(float(default_lot), 10.0))

    max_lot = risk_cfg.get("max_lot_size", 0.10)
    risk_cfg["max_lot_size"] = max(0.001, min(float(max_lot), 100.0))

    trail_mult = risk_cfg.get("trailing_stop_atr_mult", 1.5)
    risk_cfg["trailing_stop_atr_mult"] = max(0.1, min(float(trail_mult), 5.0))

    trail_start = risk_cfg.get("trailing_start_rr", 1.0)
    risk_cfg["trailing_start_rr"] = max(0.1, min(float(trail_start), 10.0))

    be_after = risk_cfg.get("break_even_after_rr", 1.0)
    risk_cfg["break_even_after_rr"] = max(0.1, min(float(be_after), 10.0))

    partial_tp = risk_cfg.get("partial_tp_rr", 1.0)
    risk_cfg["partial_tp_rr"] = max(0.1, min(float(partial_tp), 10.0))

    # Validate tp_levels: list of {rr, close_pct}
    tp_levels = risk_cfg.get("tp_levels")
    if tp_levels and isinstance(tp_levels, list):
        valid_levels = []
        for level in tp_levels:
            if isinstance(level, dict) and "rr" in level and "close_pct" in level:
                rr = max(0.1, min(float(level["rr"]), 100.0))
                pct = max(1.0, min(float(level["close_pct"]), 100.0))
                valid_levels.append({"rr": rr, "close_pct": pct})
        risk_cfg["tp_levels"] = valid_levels

    # Validate backtest section
    if "backtest" not in validated:
        validated["backtest"] = {}
    backtest_cfg = validated["backtest"]
    backtest_cfg.setdefault("default_symbol", "XAUUSD")
    backtest_cfg.setdefault("default_timeframe", "H1")
    backtest_cfg.setdefault("default_bars", 5000)
    backtest_cfg.setdefault("initial_balance", 10000)
    backtest_cfg.setdefault("commission_per_lot", 7.0)
    backtest_cfg.setdefault("spread_points", 30)

    bars = backtest_cfg.get("default_bars", 5000)
    backtest_cfg["default_bars"] = max(100, min(int(bars), 100000))

    init_bal = backtest_cfg.get("initial_balance", 10000)
    backtest_cfg["initial_balance"] = max(1000, min(float(init_bal), 1000000))

    commission = backtest_cfg.get("commission_per_lot", 7.0)
    backtest_cfg["commission_per_lot"] = max(0.0, min(float(commission), 100.0))

    spread = backtest_cfg.get("spread_points", 30)
    backtest_cfg["spread_points"] = max(0, min(int(spread), 500))

    return validated


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Return the parsed config.yaml as a nested dict (cached)."""
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}
    return _validate_config(raw_config)


def reload_config() -> dict[str, Any]:
    """Clear the cache and reload — used by the Settings page after edits."""
    get_config.cache_clear()
    return get_config()


def get_env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


def get_trading_mode() -> str:
    """Resolve effective trading mode (mock | demo)."""
    mode = (os.getenv("TRADING_MODE") or "demo").lower().strip()
    return mode if mode in {"mock", "demo"} else "demo"
