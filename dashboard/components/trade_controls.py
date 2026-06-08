"""Trade control panel — Buy/Sell/Close All, lot size slider, emergency stop."""
from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard.state import get_client, get_control_bus


def render(symbol: str, default_lot: float = 0.01) -> None:
    bus = get_control_bus()
    client = get_client()

    st.subheader("Manual Trade Controls")
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    lot = st.number_input("Lot size", min_value=0.01, max_value=10.0,
                          value=float(default_lot), step=0.01, key="manual_lot")

    if c1.button("BUY", width="stretch", type="primary"):
        try:
            r = client.place_order(symbol, "BUY", float(lot), comment="manual_buy")
            bus.push({"type": "BUY", "lot": float(lot), "result": r})
            st.success(f"Market BUY sent — {r}")
        except Exception as e:  # noqa: BLE001
            st.error(f"BUY failed: {e}")
    if c2.button("SELL", width="stretch"):
        try:
            r = client.place_order(symbol, "SELL", float(lot), comment="manual_sell")
            bus.push({"type": "SELL", "lot": float(lot), "result": r})
            st.success(f"Market SELL sent — {r}")
        except Exception as e:  # noqa: BLE001
            st.error(f"SELL failed: {e}")
    if c3.button("CLOSE ALL", width="stretch"):
        closed = 0
        for p in client.get_positions(symbol=symbol):
            if client.close_position(p["ticket"]):
                closed += 1
        bus.push({"type": "CLOSE_ALL", "closed": closed})
        st.warning(f"Closed {closed} position(s)")
    ks_state = "ENGAGED" if bus.kill_switch else "OFF"
    if c4.button(f"EMERGENCY STOP ({ks_state})", width="stretch", type="secondary"):
        new_state = bus.toggle_kill()
        if new_state:
            closed = 0
            for p in client.get_positions(symbol=symbol):
                if client.close_position(p["ticket"]):
                    closed += 1
            st.error(f"KILL SWITCH ON — closed {closed} open position(s)")
        else:
            st.info("Kill switch released")

    if bus.kill_switch:
        st.error("EMERGENCY STOP ENGAGED — the bot will not open new positions.")
