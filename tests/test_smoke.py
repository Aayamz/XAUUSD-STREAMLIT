"""Smoke test — verifies the strategy and backtester run end-to-end with the
mock client (no MT5 required)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backtester.engine import Backtester
from data.indicators import add_indicators
from mt5_connector.mock_client import MockMT5Client
from strategy.luxalgo_smc import LuxAlgoSMC


def test_strategy_runs():
    client = MockMT5Client()
    client.connect()
    df = client.get_ohlcv("XAUUSD", "H1", 500)
    df = add_indicators(df)
    df_htf = client.get_ohlcv("XAUUSD", "H4", 300)
    sig = LuxAlgoSMC().generate_signal(df, df_htf=df_htf, symbol="XAUUSD")
    assert sig is not None
    assert sig.direction.value in {"LONG", "SHORT", "NEUTRAL"}
    print(f"[smoke] signal = {sig.direction.value} conf={sig.confidence:.0f} entry={sig.entry}")


def test_backtest_runs():
    client = MockMT5Client()
    client.connect()
    df = client.get_ohlcv("XAUUSD", "H1", 1000)
    df_htf = client.get_ohlcv("XAUUSD", "H4", 600)
    result = Backtester(df, df_htf=df_htf).run()
    assert result.metrics["trades"] >= 0
    print(f"[smoke] backtest = {result.metrics}")


if __name__ == "__main__":
    test_strategy_runs()
    test_backtest_runs()
    print("[smoke] OK")
