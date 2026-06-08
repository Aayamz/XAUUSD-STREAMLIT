"""Quick test: run the strategy on the most recent bars and print the signal."""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from utils.config import get_config
from data.fetcher import DataFetcher
from mt5_connector.factory import build_client
from strategy.luxalgo_smc import LuxAlgoSMC

cfg = get_config()
client = build_client()
print(f"Client: {getattr(client, 'name', type(client).__name__)}, connected={client.is_connected()}")
symbol = cfg.get("app", {}).get("symbol", "XAUUSD")
info = client.get_symbol_info(symbol)
print(f"Symbol: {symbol}  bid={info.get('bid'):.2f}  ask={info.get('ask'):.2f}" if info else "no symbol info")

fetcher = DataFetcher(client)

for mode in ("swing", "scalp"):
    print("\n" + "=" * 60)
    print(f"MODE: {mode.upper()}")
    print("=" * 60)
    strategy = LuxAlgoSMC(cfg.get("strategy", {}), mode=mode)
    if mode == "scalp":
        htf = cfg["strategy"].get("scalp_higher_timeframe", "M15")
        ltf = cfg["strategy"].get("scalp_entry_timeframe", "M5")
    else:
        htf = cfg["strategy"].get("higher_timeframe", "H4")
        ltf = cfg["strategy"].get("entry_timeframe", "M15")
    print(f"Timeframes: HTF={htf}  LTF={ltf}")
    try:
        df_ltf = fetcher.get_bars(symbol, ltf, 300)
        df_htf = fetcher.get_bars(symbol, htf, 300) if htf else None
        print(f"Bars: LTF={len(df_ltf)}  HTF={len(df_htf) if df_htf is not None else 0}")
    except Exception as e:
        print(f"Failed to fetch bars: {e}")
        continue
    sig = strategy.generate_signal(df_ltf, df_htf=df_htf, symbol=symbol)
    print(f"Direction : {sig.direction.value}")
    print(f"Confidence: {sig.confidence:.1f}%")
    print(f"Entry/SL/TP/RR: {sig.entry:.2f} / {sig.stop_loss:.2f} / {sig.take_profit:.2f} / {sig.rr:.2f}")
    print(f"HTF bias  : {sig.htf_bias}")
    print(f"Reasons   :")
    for r in sig.reasons:
        print(f"   • {r}")
    # actionability per mode
    conf_thr = 50.0 if mode == "scalp" else 55.0
    min_rr = 1.0 if mode == "scalp" else 2.0
    actionable = (
        sig.direction.value != "NEUTRAL"
        and sig.confidence >= conf_thr
        and sig.entry > 0
        and sig.rr >= min_rr
    )
    print(f"Actionable: {actionable}")
