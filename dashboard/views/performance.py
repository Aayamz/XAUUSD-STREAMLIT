"""Performance page — equity curve, monthly/weekly stats, risk metrics.

P&L is sourced from MT5 history deals (``get_history_deals``) which return a
``profit`` field per closed trade. We map that to ``pnl`` for the stats layer.
The local ``trades.jsonl`` is a journal of bot events (open/close) and is
shown separately, never used for P&L math.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from dashboard.components.chart import build_equity_curve
from dashboard.state import fetch_history
from utils.config import PROJECT_ROOT


TRADES_LOG = Path(PROJECT_ROOT / "logs" / "trades.jsonl")


def _load_journal() -> pd.DataFrame:
    """Load bot's event journal from trades.jsonl (open/close events)."""
    if not TRADES_LOG.exists():
        return pd.DataFrame()
    rows = []
    for line in TRADES_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce")
    return df


def _load_deals_pnl(symbol: str, days: int = 90) -> pd.DataFrame:
    """Load closed trade P&L from MT5 history deals.

    Returns a DataFrame with columns: ``ts``, ``pnl``, ``symbol``, ``ticket``,
    ``volume``, ``type``, ``price``. Empty DataFrame if no deals found.
    """
    try:
        raw = fetch_history(days=days)
    except Exception as e:
        st.warning(f"Could not load MT5 history: {e}")
        return pd.DataFrame()

    if not raw:
        return pd.DataFrame()

    rows = []
    for d in raw:
        # Filter to symbol if provided and deal has one
        if symbol and d.get("symbol") and d["symbol"] != symbol:
            continue
        # PnL = profit + swap + commission (the broker's net realised P&L)
        profit = float(d.get("profit", 0) or 0)
        swap = float(d.get("swap", 0) or 0)
        commission = float(d.get("commission", 0) or 0)
        pnl = profit + swap + commission
        # Skip DEAL_ENTRY rows (position open) which typically have profit=0
        entry_flag = int(d.get("entry", 0) or 0)
        if entry_flag == 0 and profit == 0 and swap == 0:
            continue
        rows.append({
            "ts": d.get("time", 0),
            "pnl": pnl,
            "profit": profit,
            "swap": swap,
            "commission": commission,
            "symbol": d.get("symbol", ""),
            "ticket": d.get("ticket", d.get("deal", 0)),
            "volume": d.get("volume", 0),
            "type": d.get("type", 0),
            "price": d.get("price", 0),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    return df


def _stats(df: pd.DataFrame) -> dict:
    if df.empty or "pnl" not in df.columns:
        return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "net_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    pnl = df["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    pf = (wins.sum() / -losses.sum()) if len(losses) and losses.sum() != 0 else float("inf")
    return {
        "trades": int(len(pnl)),
        "win_rate": float((len(wins) / len(pnl) * 100) if len(pnl) else 0.0),
        "profit_factor": float(pf) if np.isfinite(pf) else 99.99,
        "net_pnl": float(pnl.sum()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
    }


def _group_stats(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    if df.empty or "pnl" not in df.columns or "ts" not in df.columns:
        return pd.DataFrame(columns=["ts", "pnl"])
    grouped = df.set_index("ts").resample(freq)["pnl"].sum().fillna(0.0)
    return grouped.reset_index()


def _demo_curve() -> pd.Series:
    idx = pd.date_range(end=pd.Timestamp.utcnow(), periods=60, freq="1H", tz="UTC")
    return pd.Series(
        10_000 + np.cumsum(np.random.default_rng(0).normal(0, 5, len(idx))),
        index=idx,
    )


def render() -> None:
    from dashboard.styles import inject_global_styles
    inject_global_styles()

    symbol = st.session_state.get("symbol", "XAUUSD")
    lookback = st.sidebar.slider("Lookback (days)", 7, 365, 90, key="perf_lookback") \
        if hasattr(st, "sidebar") else 90

    df = _load_deals_pnl(symbol, days=lookback)
    journal = _load_journal()

    if df.empty:
        st.info("No closed trades in the last %d days — close a position to see P&L stats." % lookback)
        st.plotly_chart(build_equity_curve(_demo_curve()), width="stretch")
        st.caption("Demo equity curve (no closed trades).")
    else:
        stats = _stats(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trades", stats["trades"])
        c2.metric("Win rate", f"{stats['win_rate']:.1f}%")
        c3.metric("Profit factor", f"{stats['profit_factor']:.2f}")
        c4.metric("Net P&L", f"${stats['net_pnl']:+.2f}")

        # Equity curve from cumulative pnl (starting at 0, can be offset by starting balance)
        eq = pd.Series(
            df["pnl"].cumsum().values,
            index=df["ts"],
            name="equity",
        )
        st.plotly_chart(build_equity_curve(eq), width="stretch")
        st.caption(f"Cumulative P&L across {len(df)} closed trade(s).")

        st.subheader("By Week")
        st.dataframe(_group_stats(df, "W"), width="stretch", hide_index=True)

        st.subheader("By Month")
        st.dataframe(_group_stats(df, "ME"), width="stretch", hide_index=True)

        st.subheader("Closed trades (from MT5 history)")
        st.dataframe(df.tail(100), width="stretch", hide_index=True)

    # Journal from bot's local log (separate from P&L)
    st.subheader("Bot journal (trades.jsonl)")
    if journal.empty:
        st.caption("No events logged yet.")
    else:
        st.dataframe(journal.tail(100), width="stretch", hide_index=True)
