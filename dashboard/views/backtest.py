"""Backtest page — run a quick backtest on the available history."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from backtester.engine import Backtester
from dashboard.components.chart import build_equity_curve
from dashboard.state import fetch_bars
from utils.config import PROJECT_ROOT


def _df_from_trades(trades) -> pd.DataFrame:
    rows = []
    for t in trades:
        rows.append(
            {
                "side": t.side,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry": t.entry_price,
                "exit": t.exit_price,
                "pnl": round(t.pnl, 2),
                "reason": t.reason,
            }
        )
    return pd.DataFrame(rows)


def render() -> None:
    from dashboard.styles import inject_global_styles
    inject_global_styles()

    symbol = st.session_state.get("symbol", "XAUUSD")
    st.subheader("Quick Backtest")
    c1, c2, c3 = st.columns(3)
    tf = c1.selectbox("Timeframe", ["M5", "M15", "H1", "H4", "D1"], index=2)
    bars = c2.slider("Bars", 500, 5000, 2000, step=500)
    risk = c3.number_input("Risk %", min_value=0.1, max_value=5.0, value=1.0, step=0.1)

    if st.button("Run backtest", type="primary"):
        with st.spinner("Running…"):
            try:
                df_ltf = fetch_bars(symbol, tf, bars)
                df_htf = fetch_bars(symbol, "H4", min(bars // 4, 1000))
            except Exception as e:  # noqa: BLE001
                st.error(f"Failed to load bars: {e}")
                return
            bt = Backtester(df_ltf=df_ltf, df_htf=df_htf, risk_pct=risk, strategy_mode=st.session_state.get("strategy_mode", "swing"))
            result = bt.run()
            st.session_state["bt_result"] = result

    result = st.session_state.get("bt_result")
    if not result:
        st.info("Adjust parameters and click **Run backtest**.")
        return

    m = result.metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Trades", m.get("trades", 0))
    c2.metric("Win rate", f"{m.get('win_rate_pct', 0):.1f}%")
    c3.metric("Profit factor", f"{m.get('profit_factor', 0):.2f}")
    c4.metric("Net P&L", f"${m.get('net_pnl', 0):+.2f}")
    c5.metric("Max DD", f"{m.get('max_drawdown_pct', 0):.2f}%")

    if not result.equity_curve.empty:
        st.plotly_chart(build_equity_curve(result.equity_curve), width="stretch")

    df_trades = _df_from_trades(result.trades)
    if not df_trades.empty:
        st.dataframe(df_trades, width="stretch", hide_index=True)
        # save to file for the Performance page
        out = Path(PROJECT_ROOT / "logs" / "trades.jsonl")
        out.parent.mkdir(exist_ok=True)
        with out.open("a", encoding="utf-8") as f:
            for _, row in df_trades.iterrows():
                f.write(json.dumps({"ts": pd.Timestamp(row["entry_time"]).timestamp(),
                                    **row.to_dict()}) + "\n")
        st.caption(f"Appended {len(df_trades)} trades to logs/trades.jsonl")
    else:
        st.warning("No trades were generated during the backtest period.")
