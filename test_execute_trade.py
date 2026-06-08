"""End-to-end test: push a MANUAL_TRADE command and run one bot tick.

Run from the project root:

    .venv\\Scripts\\python.exe test_execute_trade.py

Expected output:
  - "Bot constructed"
  - "MANUAL_TRADE command pushed"
  - "place_order response: {'retcode': 10009, ... 'ok': True}"
  - "Opened BUY 0.10 @ ... ticket=..."

Verify in MT5 terminal that a new position ticket appears.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")


def close_position(client, symbol: str, p: dict) -> bool:
    """Close a single MT5 position and return True if successful."""
    try:
        result = client.close_position(p["ticket"])
        print(f"     Closed position ticket={p['ticket']} "
              f"{p['type']} {p['volume']} @ {p['price_open']}")
        return result
    except Exception as e:
        print(f"     Failed to close ticket={p['ticket']}: {e}")
        return False


def main() -> int:
    print("=" * 60)
    print("XAUUSD SMC Bot — manual trade end-to-end test")
    print("=" * 60)

    from bot import TradingBot
    from dashboard.state import ControlBus

    # 1) Build a bot — this connects to MT5 (real or mock)
    print("\n[1/4] Building TradingBot (connects to MT5)...")
    bot = TradingBot()
    print(f"     Client name : {getattr(bot.client, 'name', type(bot.client).__name__)}")
    print(f"     Symbol      : {bot.symbol}")
    print(f"     Connected   : {bot.client.is_connected()}")

    # Close any existing positions first so the test order goes through
    try:
        existing = bot.client.get_positions(symbol=bot.symbol)
        if existing:
            print(f"\n     Closing {len(existing)} existing position(s)...")
            for p in existing:
                close_position(bot.client, bot.symbol, p)
            time.sleep(0.5)  # wait for MT5 to process
    except Exception as e:
        print(f"     Could not check/close positions: {e}")

    # 2) Build a synthetic actionable signal that aligns with current price
    print("\n[2/4] Building a synthetic actionable LONG signal...")
    info = bot.client.get_symbol_info(bot.symbol)
    if info is None or float(info.get("bid", 0)) == 0:
        print("     ERROR: cannot read symbol info — aborting")
        return 1
    bid = float(info["bid"])
    ask = float(info["ask"])
    stops = int(info.get("trade_stops_level", 0) or 0)
    point = float(info.get("point", 0.01))
    min_stop = stops * point
    entry = ask
    risk = max(5.0, min_stop * 2)   # at least 2x broker min stop distance
    sl = round(bid - risk, 2)
    tp = round(ask + risk * 2.0, 2)  # RR ≈ 2
    print(f"     Bid {bid:.2f}  Ask {ask:.2f}")
    print(f"     Broker min stops: {min_stop:.2f} USD")
    print(f"     Risk distance    : {risk:.2f}")
    print(f"     Synth signal: BUY  entry={entry:.2f}  sl={sl:.2f}  tp={tp:.2f}  rr=2.0")

    signal_data = {
        "direction": "LONG",
        "confidence": 80.0,
        "entry": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "rr": 2.0,
        "reasons": ["test:synthetic"],
        "timestamp": time.time(),
        "is_actionable": True,
        "strategy_mode": "swing",
        "htf_bias": "BULL",
    }

    # 3) Inject the manual trade command onto the control bus
    print("\n[3/4] Pushing MANUAL_TRADE command onto control bus...")
    bus = ControlBus()
    bus.push({"type": "MANUAL_TRADE", "signal_data": signal_data})
    print(f"     Pending commands: {len(bus.commands)}")

    # 4) Run one tick — the bot drains the bus and calls _open_trade
    print("\n[4/4] Running bot.tick() — this will drain commands and place order...")
    import dashboard.state as state_mod
    original_get = state_mod.get_control_bus
    state_mod.get_control_bus = lambda: bus
    try:
        sig = bot.tick()
    finally:
        state_mod.get_control_bus = original_get

    print("\n" + "-" * 60)
    print("Tick complete. Auto signal:")
    if sig is not None:
        print(f"  direction  = {sig.direction.value}")
        print(f"  confidence = {sig.confidence:.1f}%")
        print(f"  entry/sl/tp= {sig.entry:.2f} / {sig.stop_loss:.2f} / {sig.take_profit:.2f}")
    else:
        print("  (no signal returned — likely a bars / MT5 error)")

    # 5) Check open positions after the test
    print("\nFinal positions in MT5:")
    try:
        positions = bot.client.get_positions(symbol=bot.symbol)
        if not positions:
            print("  (none)")
        for p in positions:
            print(f"  ticket={p.get('ticket')}  type={p.get('type')}  "
                  f"vol={p.get('volume')}  open={p.get('price_open')}  "
                  f"sl={p.get('sl')}  tp={p.get('tp')}")
    except Exception as e:
        print(f"  could not read positions: {e}")

    print("\n" + "=" * 60)
    print("Done. Check MT5 terminal for a new position ticket.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
