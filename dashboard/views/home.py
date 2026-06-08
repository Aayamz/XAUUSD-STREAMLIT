"""Overview / home page — at-a-glance status with modern card layout."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard.components.metrics import (
    render_account, render_market, render_perf,
)
from dashboard.state import (
    fetch_account, fetch_bars, fetch_history, fetch_positions, fetch_symbol_info,
    get_bot_runner, get_client, get_control_bus, get_strategy,
)
from strategy.luxalgo_smc import Direction
from utils.config import PROJECT_ROOT


SIGNAL_LOG = PROJECT_ROOT / "logs" / "signals.jsonl"


def _load_recent_signals(limit: int = 6) -> list[dict]:
    if not SIGNAL_LOG.exists():
        return []
    out = []
    for line in SIGNAL_LOG.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(out))


def _signal_badge(direction: str) -> str:
    return {
        "LONG":   "xc-badge-long",
        "SHORT":  "xc-badge-short",
        "NEUTRAL":"xc-badge-neutral",
    }.get(direction, "xc-badge-neutral")


def render() -> None:
    st_autorefresh(interval=10_000, key="home_refresh")
    symbol = st.session_state.get("symbol", "XAUUSD")
    cfg = st.session_state.get("cfg", {})
    ltf = cfg.get("strategy", {}).get("entry_timeframe", "M15")
    htf = cfg.get("strategy", {}).get("higher_timeframe", "H4")
    strategy_mode = st.session_state.get("strategy_mode", "swing")

    # ---- Market data ---------------------------------------------------------
    try:
        account  = fetch_account()
        info     = fetch_symbol_info(symbol)
        positions = fetch_positions(symbol)
    except Exception as e:  # noqa: BLE001
        st.error(f"MT5 not reachable: {e}")
        return

    st.markdown('<p class="xc-section-title">Market</p>', unsafe_allow_html=True)
    render_market(info)

    st.markdown('<p class="xc-section-title">Account</p>', unsafe_allow_html=True)
    render_account(account)

    # ---- Performance summary (closed deals from MT5) ------------------------
    try:
        deals = fetch_history(days=30)
        daily_pnl, win_rate, pf, trades = 0.0, 0.0, 0.0, 0
        if deals:
            pnls = [float(d.get("profit", 0) or 0)
                    + float(d.get("swap", 0) or 0)
                    + float(d.get("commission", 0) or 0)
                    for d in deals]
            daily_pnl = sum(pnls)
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p <= 0]
            trades = len(pnls)
            if trades:
                win_rate = len(wins) / trades * 100
                if losses and sum(losses) != 0:
                    pf = sum(wins) / abs(sum(losses))
    except Exception:
        daily_pnl, win_rate, pf, trades = 0.0, 0.0, 0.0, 0

    st.markdown('<p class="xc-section-title">Performance (30d)</p>', unsafe_allow_html=True)
    render_perf(
        perf={"daily_pnl": daily_pnl, "win_rate": win_rate,
              "profit_factor": pf, "trades": trades},
        positions=positions,
    )

    # ---- Latest signal + Manual trade ----------------------------------------
    st.markdown('<p class="xc-section-title">Latest Signal</p>', unsafe_allow_html=True)
    _render_latest_signal(symbol, cfg, ltf, htf, strategy_mode)

    # ---- Recent signals (compact) --------------------------------------------
    st.markdown('<p class="xc-section-title">Recent Signals</p>', unsafe_allow_html=True)
    _render_recent_signals()


def _render_latest_signal(symbol: str, cfg: dict, ltf: str, htf: str,
                          strategy_mode: str) -> None:
    try:
        df_ltf = fetch_bars(symbol, ltf, 300)
        df_htf = fetch_bars(symbol, htf, 300) if htf else None
        sig = get_strategy(
            strategy_mode,
            strategy_name=st.session_state.get("active_strategy"),
        ).generate_signal(df_ltf, df_htf=df_htf, symbol=symbol)
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to compute signal: {e}")
        return
    if sig is None:
        return

    direction = sig.direction.value
    badge_cls = _signal_badge(direction)
    conf = float(sig.confidence)
    conf_tone = "up" if conf >= 70 else "accent" if conf >= 55 else "down"
    confidence_threshold = 50.0 if strategy_mode == "scalp" else 55.0
    min_rr = 1.0 if strategy_mode == "scalp" else 2.0
    is_actionable = (
        direction != "NEUTRAL"
        and conf >= confidence_threshold
        and sig.entry > 0
        and sig.stop_loss > 0
        and sig.take_profit > 0
        and sig.rr >= min_rr
    )

    # Save to control bus for manual trade
    bus = get_control_bus()
    bus.update_signal({
        "direction": direction,
        "confidence": conf,
        "entry": sig.entry,
        "stop_loss": sig.stop_loss,
        "take_profit": sig.take_profit,
        "rr": sig.rr,
        "reasons": sig.reasons,
        "timestamp": sig.timestamp,
        "is_actionable": is_actionable,
        "strategy_mode": strategy_mode,
    })

    # Layout
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(
            f"""
            <div class="xc-card">
              <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
                <span class="xc-badge {badge_cls}">{direction}</span>
                <span style="color:var(--text-muted);font-size:0.8rem">HTF bias: {sig.htf_bias}</span>
                <span style="margin-left:auto" class="xc-stat-{conf_tone}">
                  <b>{conf:.0f}%</b> confidence
                </span>
              </div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:14px">
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em">Entry</div>
                  <div style="font-size:1.2rem;font-weight:600">{sig.entry:.2f}</div>
                </div>
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em">Stop</div>
                  <div style="font-size:1.2rem;font-weight:600" class="xc-pnl-neg">{sig.stop_loss:.2f}</div>
                </div>
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em">Target</div>
                  <div style="font-size:1.2rem;font-weight:600" class="xc-pnl-pos">{sig.take_profit:.2f}</div>
                </div>
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em">R:R</div>
                  <div style="font-size:1.2rem;font-weight:600" class="xc-stat-accent">{sig.rr:.2f}</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if is_actionable:
            st.markdown(
                f"""
                <div class="xc-badge xc-badge-live" style="margin-top:10px">
                  <span class="xc-dot"></span> ACTIONABLE · {strategy_mode.upper()}
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            with st.expander("Why not actionable?", expanded=False):
                if direction == "NEUTRAL":
                    st.write("• Direction is NEUTRAL")
                if conf < confidence_threshold:
                    st.write(f"• Confidence {conf:.1f}% < {confidence_threshold}% threshold")
                if sig.entry <= 0:
                    st.write("• Invalid entry price")
                if sig.stop_loss <= 0:
                    st.write("• Invalid stop loss")
                if sig.take_profit <= 0:
                    st.write("• Invalid take profit")
                if sig.rr < min_rr:
                    st.write(f"• R:R {sig.rr:.2f} < {min_rr} minimum")

    with col2:
        reasons_items = "".join(f"<li>{r}</li>" for r in sig.reasons)
        st.markdown(
            f"""
            <div class="xc-card">
              <p class="xc-section-title" style="margin-top:0">Reasons</p>
              <ul class="xc-reasons-list">{reasons_items}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Manual trade button
    if is_actionable:
        if st.button("Execute Trade Now", type="primary", width="stretch",
                     key="execute_signal"):
            bus.push({"type": "MANUAL_TRADE", "signal_data": bus.get_last_signal()})
            st.toast("Trade queued — runs on next bot tick.", icon="🚀")


def _render_recent_signals() -> None:
    recent = _load_recent_signals(6)
    if not recent:
        st.markdown(
            "<div class='xc-card-flat' style='text-align:center;color:var(--text-muted);"
            "padding:18px'>No signals logged yet. Run the bot to generate signals.</div>",
            unsafe_allow_html=True,
        )
        return

    # Use st.columns for layout — CSS grid breaks inside Streamlit markdown
    rows = [recent[i:i+3] for i in range(0, len(recent), 3)]
    for row in rows:
        cols = st.columns(len(row))
        for i, s in enumerate(row):
            d = s.get("direction", "\u2014")
            cls = _signal_badge(d)
            conf = float(s.get("confidence", 0))
            ts = pd.to_datetime(s.get("ts", 0), unit="s", utc=True, errors="coerce")
            time_str = ts.strftime("%H:%M:%S") if pd.notna(ts) else "\u2014"
            with cols[i]:
                st.markdown(
                    f"""
                    <div class="xc-card" style="padding:10px 14px;margin-bottom:8px">
                      <div style="display:flex;align-items:center;gap:8px">
                        <span class="xc-badge {cls}" style="font-size:0.65rem">{d}</span>
                        <span style="color:var(--text-muted);font-size:0.75rem">{time_str}</span>
                        <span style="margin-left:auto;font-weight:600;font-size:0.9rem">{conf:.0f}%</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
