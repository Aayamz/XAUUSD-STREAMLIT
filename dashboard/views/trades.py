"""Trades page — open positions (MT5) + history (MT5) + manual trade controls.

The history is sourced directly from MT5 via ``get_history_deals`` so it shows
closed positions with their actual realised P&L, swap, and commission.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard.state import (
    fetch_history, fetch_positions, get_bot_runner, get_client, get_control_bus,
)
from strategy.luxalgo_smc import Direction


# --- Helpers ------------------------------------------------------------------
_DEAL_TYPE = {
    0: "BUY",
    1: "SELL",
    2: "BUY",     # buy by market balance
    3: "SELL",
    4: "BUY",     # buy by margin
    5: "SELL",
}

_ENTRY_TYPE = {0: "IN", 1: "OUT", 2: "INOUT"}


def _deal_type_label(t: int) -> str:
    return _DEAL_TYPE.get(int(t), str(t))


def _entry_flag(e: int) -> str:
    return _ENTRY_TYPE.get(int(e), str(e))


def _normalize_deals(deals: list[dict]) -> pd.DataFrame:
    """Map raw MT5 deals to a tidy DataFrame.

    Each row corresponds to a single deal (open or close). For position-level
    P&L we pair IN/OUT deals later.
    """
    if not deals:
        return pd.DataFrame()

    rows = []
    for d in deals:
        profit = float(d.get("profit", 0) or 0)
        swap = float(d.get("swap", 0) or 0)
        commission = float(d.get("commission", 0) or 0)
        rows.append({
            "time": pd.to_datetime(int(d.get("time", 0)), unit="s", utc=True, errors="coerce"),
            "deal_id": d.get("deal", 0),
            "order": d.get("ticket", 0),
            "symbol": d.get("symbol", ""),
            "side": _deal_type_label(d.get("type", 0)),
            "entry": _entry_flag(d.get("entry", 0)),
            "volume": float(d.get("volume", 0) or 0),
            "price": float(d.get("price", 0) or 0),
            "profit": profit,
            "swap": swap,
            "commission": commission,
            "net": profit + swap + commission,
            "comment": d.get("comment", ""),
        })
    df = pd.DataFrame(rows).dropna(subset=["time"]).sort_values("time", ascending=False)
    return df.reset_index(drop=True)


def _build_round_trips(df: pd.DataFrame) -> pd.DataFrame:
    """Pair IN/OUT deals by order to compute per-trade P&L.

    Returns one row per closed position with: open_time, close_time, side,
    volume, open_price, close_price, pnl, swap, commission, duration.
    """
    if df.empty:
        return pd.DataFrame()

    opens = df[df["entry"] == "IN"].copy()
    closes = df[df["entry"] == "OUT"].copy()
    if closes.empty:
        return pd.DataFrame()

    out = []
    for _, c in closes.iterrows():
        order = c["order"]
        matching_opens = opens[opens["order"] == order].sort_values("time")
        if matching_opens.empty:
            continue
        o = matching_opens.iloc[-1]
        duration = c["time"] - o["time"]
        out.append({
            "close_time": c["time"],
            "open_time":  o["time"],
            "symbol":     c["symbol"],
            "side":       c["side"],
            "volume":     o["volume"],
            "open":       float(o["price"]),
            "close":      float(c["price"]),
            "pnl":        float(c["profit"]),
            "swap":       float(c["swap"]),
            "commission": float(c["commission"]),
            "net":        float(c["profit"]) + float(c["swap"]) + float(c["commission"]),
            "duration":   duration,
        })
    if not out:
        return pd.DataFrame()
    return pd.DataFrame(out).sort_values("close_time", ascending=False).reset_index(drop=True)


def _pips(side: str, op: float, cl: float, point: float) -> float:
    if not point:
        return 0.0
    diff = (cl - op) if side == "BUY" else (op - cl)
    return diff / point


def _positions_table(positions: list[dict]) -> pd.DataFrame:
    if not positions:
        return pd.DataFrame()
    df = pd.DataFrame(positions)
    if "time" in df.columns:
        df["opened"] = pd.to_datetime(df["time"], unit="s", utc=True, errors="coerce")
    return df


def _signed_money(v: float, decimals: int = 2) -> str:
    """Format a signed dollar value using a real minus sign (\u2212)."""
    if v > 0:
        return f"+${abs(v):,.{decimals}f}"
    if v < 0:
        return f"\u2212${abs(v):,.{decimals}f}"
    return f"${0:,.{decimals}f}"


# --- Page ---------------------------------------------------------------------
def render() -> None:
    symbol = st.session_state.get("symbol", "XAUUSD")
    st_autorefresh(interval=10_000, key="trades_refresh")

    # ===== Open Positions =====================================================
    st.markdown('<p class="xc-section-title">Open Positions</p>', unsafe_allow_html=True)
    try:
        positions = fetch_positions(symbol)
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to load positions: {e}")
        positions = []

    if not positions:
        st.markdown(
            "<div class='xc-card-flat' style='text-align:center;color:var(--text-muted);"
            "padding:24px'>No open positions. Place a manual trade below or wait for an auto signal.</div>",
            unsafe_allow_html=True,
        )
    else:
        for p in positions:
            _render_open_position(p)

    # ===== Manual trade controls =============================================
    st.markdown('<p class="xc-section-title">Manual Trade</p>', unsafe_allow_html=True)
    _render_manual_trade(symbol)

    # ===== Trade history =====================================================
    st.markdown('<p class="xc-section-title">Trade History</p>', unsafe_allow_html=True)
    _render_history(symbol)


def _render_open_position(p: dict) -> None:
    side = p.get("type", "BUY")
    side_class = "xc-badge-long" if side == "BUY" else "xc-badge-short"
    profit = float(p.get("profit", 0) or 0)
    pnl_class = "xc-pnl-pos" if profit > 0 else ("xc-pnl-neg" if profit < 0 else "xc-pnl-zero")
    pnl_str = _signed_money(profit)

    st.markdown(
        f"""
        <div class="xc-card" style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
            <div>
              <span class="xc-badge {side_class}">{side}</span>
              <span style="margin-left:8px;font-weight:600">{p.get('volume', 0)} lots</span>
              <span style="margin-left:8px;color:var(--text-muted)">@ {p.get('price_open', 0):.2f}</span>
            </div>
            <div>
              <span class="{pnl_class}">{pnl_str}</span>
            </div>
          </div>
          <div style="margin-top:8px;color:var(--text-muted);font-size:0.8rem">
            Ticket <code>{p.get('ticket')}</code>
            &nbsp;·&nbsp; SL {p.get('sl') or '—':.2f}
            &nbsp;·&nbsp; TP {p.get('tp') or '—':.2f}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Manage position", expanded=False):
        c1, c2, c3 = st.columns([2, 1, 1])
        new_sl = c1.number_input("New SL", value=float(p.get("sl") or 0.0),
                                 key=f"sl_{p['ticket']}", format="%.2f")
        new_tp = c2.number_input("New TP", value=float(p.get("tp") or 0.0),
                                 key=f"tp_{p['ticket']}", format="%.2f")
        if c3.button("Update", key=f"upd_{p['ticket']}", type="primary"):
            try:
                get_client().modify_position(p["ticket"], sl=new_sl or None, tp=new_tp or None)
                st.success(f"Updated ticket {p['ticket']}.")
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(f"Update failed: {e}")
        if c3.button("Close", key=f"close_{p['ticket']}"):
            try:
                ok = get_client().close_position(p["ticket"])
                if ok:
                    st.success(f"Closed ticket {p['ticket']}.")
                    st.rerun()
                else:
                    st.error("Close returned False.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Close failed: {e}")


def _render_manual_trade(symbol: str) -> None:
    """Manual trade panel — uses the bot's signal pipeline + control bus."""
    bus = get_control_bus()
    runner = get_bot_runner()
    last_sig = bus.get_last_signal()

    if last_sig and last_sig.get("is_actionable"):
        direction = last_sig.get("direction", "NEUTRAL")
        side_class = ("xc-badge-long" if direction == "LONG"
                      else "xc-badge-short" if direction == "SHORT"
                      else "xc-badge-neutral")
        conf = float(last_sig.get("confidence", 0))
        conf_tone = ("up" if conf >= 70 else "accent" if conf >= 55 else "down")
        st.markdown(
            f"""
            <div class="xc-card" style="margin-bottom:10px">
              <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <span class="xc-badge {side_class}">{direction}</span>
                <span style="color:var(--text-muted)">latest actionable signal</span>
                <span style="margin-left:auto" class="xc-stat-{conf_tone}">
                  <b>{conf:.0f}%</b> confidence
                </span>
              </div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px">
                <div><span style="color:var(--text-muted);font-size:0.7rem">ENTRY</span><br>
                  <b>{last_sig.get('entry', 0):.2f}</b></div>
                <div><span style="color:var(--text-muted);font-size:0.7rem">STOP</span><br>
                  <b class="xc-pnl-neg">{last_sig.get('stop_loss', 0):.2f}</b></div>
                <div><span style="color:var(--text-muted);font-size:0.7rem">TARGET</span><br>
                  <b class="xc-pnl-pos">{last_sig.get('take_profit', 0):.2f}</b></div>
                <div><span style="color:var(--text-muted);font-size:0.7rem">R:R</span><br>
                  <b class="xc-stat-accent">{last_sig.get('rr', 0):.2f}</b></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='xc-card-flat' style='color:var(--text-muted);text-align:center;'>"
            "No actionable signal yet. See the Signals page."
            "</div>",
            unsafe_allow_html=True,
        )

    c1, c2, c3 = st.columns([1, 1, 1])
    if c1.button("Execute Last Signal", type="primary", width="stretch",
                 disabled=not (last_sig and last_sig.get("is_actionable"))):
        if last_sig and last_sig.get("is_actionable"):
            bus.push({"type": "MANUAL_TRADE", "signal_data": last_sig})
            st.toast("Trade command queued — will execute on next bot tick.", icon="🚀")
        else:
            st.warning("No actionable signal to execute.")

    if c2.button("Run Strategy Tick", width="stretch"):
        try:
            from bot import TradingBot
            bot = TradingBot()
            bot.tick()
            st.success("Tick completed.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Tick failed: {e}")

    if c3.button("Close All Positions", width="stretch"):
        closed = 0
        for p in positions if (positions := fetch_positions(symbol)) else []:
            try:
                if get_client().close_position(p["ticket"]):
                    closed += 1
            except Exception:
                pass
        st.toast(f"Closed {closed} position(s).", icon="✅" if closed else "ℹ️")
        st.rerun()


def _render_history(symbol: str) -> None:
    """Fetch closed deals from MT5 and render a filterable table."""
    # Filters
    fc1, fc2, fc3 = st.columns(3)
    lookback = fc1.selectbox("Lookback", [7, 14, 30, 60, 90, 180, 365],
                             index=2, key="hist_lookback")
    side_filter = fc2.multiselect("Side", ["BUY", "SELL"],
                                  default=["BUY", "SELL"], key="hist_side")
    symbol_filter = fc3.text_input("Symbol contains", value="", key="hist_sym")

    try:
        raw = fetch_history(days=lookback)
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to load history: {e}")
        raw = []

    df = _normalize_deals(raw)
    if df.empty:
        st.markdown(
            "<div class='xc-card-flat' style='text-align:center;color:var(--text-muted);"
            "padding:24px'>No closed trades in the last %d days.</div>" % lookback,
            unsafe_allow_html=True,
        )
        return

    # Round-trip view
    rt = _build_round_trips(df)
    if not rt.empty:
        rt = rt[rt["side"].isin(side_filter)]
        if symbol_filter:
            rt = rt[rt["symbol"].str.contains(symbol_filter, case=False, na=False)]
        if rt.empty:
            st.markdown(
                "<div class='xc-card-flat' style='text-align:center;color:var(--text-muted);"
                "padding:18px'>No closed positions match the current filters.</div>",
                unsafe_allow_html=True,
            )
        else:
            _render_history_summary(rt)
            _render_history_table(rt)
    else:
        st.markdown(
            "<div class='xc-card-flat' style='text-align:center;color:var(--text-muted);"
            "padding:18px'>No completed round-trips in the selected period.</div>",
            unsafe_allow_html=True,
        )

    with st.expander("Raw deals (all entries/exits)", expanded=False):
        df_show = df.copy()
        df_show["time"] = df_show["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(df_show.head(200), width="stretch", hide_index=True)


def _render_history_summary(rt: pd.DataFrame) -> None:
    total = len(rt)
    wins = int((rt["pnl"] > 0).sum())
    losses = int((rt["pnl"] <= 0).sum())
    wr = wins / total * 100 if total else 0
    net = float(rt["net"].sum())
    avg = float(rt["net"].mean()) if total else 0
    best = float(rt["net"].max()) if total else 0
    worst = float(rt["net"].min()) if total else 0

    cols = st.columns(6)
    cols[0].markdown(
        f"<div class='xc-stat'><p class='xc-stat-label'>Trades</p>"
        f"<p class='xc-stat-value'>{total}</p></div>",
        unsafe_allow_html=True,
    )
    cols[1].markdown(
        f"<div class='xc-stat'><p class='xc-stat-label'>Win Rate</p>"
        f"<p class='xc-stat-value'>{wr:.1f}%</p>"
        f"<p class='xc-stat-sub'>{wins}W / {losses}L</p></div>",
        unsafe_allow_html=True,
    )
    tone = "up" if net > 0 else ("down" if net < 0 else "neutral")
    net_str = _signed_money(net)
    cols[2].markdown(
        f"<div class='xc-stat'><p class='xc-stat-label'>Net P&L</p>"
        f"<p class='xc-stat-value xc-stat-{tone}'>{net_str}</p></div>",
        unsafe_allow_html=True,
    )
    avg_tone = "up" if avg > 0 else ("down" if avg < 0 else "neutral")
    avg_str = _signed_money(avg)
    cols[3].markdown(
        f"<div class='xc-stat'><p class='xc-stat-label'>Avg P&L</p>"
        f"<p class='xc-stat-value xc-stat-{avg_tone}'>{avg_str}</p></div>",
        unsafe_allow_html=True,
    )
    cols[4].markdown(
        f"<div class='xc-stat'><p class='xc-stat-label'>Best</p>"
        f"<p class='xc-stat-value xc-stat-up'>${best:.2f}</p></div>",
        unsafe_allow_html=True,
    )
    cols[5].markdown(
        f"<div class='xc-stat'><p class='xc-stat-label'>Worst</p>"
        f"<p class='xc-stat-value xc-stat-down'>${worst:.2f}</p></div>",
        unsafe_allow_html=True,
    )


def _render_history_table(rt: pd.DataFrame) -> None:
    show = rt.copy()
    show["close_time"] = show["close_time"].dt.strftime("%Y-%m-%d %H:%M")
    show["duration"] = show["duration"].apply(
        lambda d: str(d).split(".")[0] if pd.notna(d) else "—"
    )
    show["pnl"] = show["pnl"].apply(_signed_money)
    show["net"] = show["net"].apply(_signed_money)
    show = show.rename(columns={
        "close_time": "Closed",
        "symbol": "Symbol",
        "side": "Side",
        "volume": "Volume",
        "open": "Open",
        "close": "Close",
        "pnl": "P&L",
        "net": "Net",
        "duration": "Duration",
    })
    cols_to_show = ["Closed", "Symbol", "Side", "Volume", "Open", "Close",
                    "P&L", "Net", "Duration"]
    st.dataframe(
        show[cols_to_show].head(200),
        width="stretch",
        hide_index=True,
        column_config={
            "Side": st.column_config.TextColumn(width="small"),
            "P&L":  st.column_config.TextColumn(width="small"),
            "Net":  st.column_config.TextColumn(width="small"),
        },
    )
