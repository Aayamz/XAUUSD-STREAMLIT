"""Signals page — current actionable signal + history log."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.state import (
    fetch_account, fetch_bars, fetch_symbol_info, get_strategy,
)
from strategy import list_strategies
from strategy.luxalgo_smc import Direction
from utils.config import PROJECT_ROOT


SIGNAL_LOG = PROJECT_ROOT / "logs" / "signals.jsonl"


def _badge(direction: str) -> str:
    return {
        "LONG":   "xc-badge-long",
        "SHORT":  "xc-badge-short",
        "NEUTRAL":"xc-badge-neutral",
    }.get(direction, "xc-badge-neutral")


def _confidence_tone(c: float) -> str:
    if c >= 70: return "up"
    if c >= 55: return "accent"
    return "down"


def _render_current(sig, account, info, strategy_name: str | None = None) -> None:
    direction = sig.direction.value
    cls = _badge(direction)
    conf = float(sig.confidence)
    tone = _confidence_tone(conf)
    eq = (account or {}).get("equity") if account else None
    eq_str = f"${eq:,.2f}" if eq else "—"
    strategy_label = next((s["label"] for s in list_strategies() if s["name"] == strategy_name), strategy_name or "—")

    cols_top = st.columns([3, 1])
    with cols_top[0]:
        st.markdown(
            f"""
            <div class="xc-card">
              <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
                <span class="xc-badge {cls}" style="font-size:0.85rem;padding:5px 12px">{direction}</span>
                <span class="xc-stat-{tone}" style="font-size:1.6rem;font-weight:700">
                  {conf:.0f}%
                </span>
                <span style="color:var(--text-muted)">HTF {sig.htf_bias}</span>
                <span style="margin-left:auto;color:var(--text-muted);font-size:0.75rem">
                  {strategy_label}
                </span>
              </div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:18px">
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em">Entry</div>
                  <div style="font-size:1.3rem;font-weight:600">{sig.entry:.2f}</div>
                </div>
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em">Stop Loss</div>
                  <div style="font-size:1.3rem;font-weight:600" class="xc-pnl-neg">{sig.stop_loss:.2f}</div>
                </div>
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em">Take Profit</div>
                  <div style="font-size:1.3rem;font-weight:600" class="xc-pnl-pos">{sig.take_profit:.2f}</div>
                </div>
                <div>
                  <div style="color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em">R:R</div>
                  <div style="font-size:1.3rem;font-weight:600" class="xc-stat-accent">{sig.rr:.2f}</div>
                </div>
              </div>
              <div style="margin-top:18px;border-top:1px solid var(--border);padding-top:14px">
                <p class="xc-section-title" style="margin:0 0 8px 0">Reasoning</p>
                <ul class="xc-reasons-list">{"".join(f"<li>{r}</li>" for r in sig.reasons)}</ul>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with cols_top[1]:
        st.markdown(
            f"""
            <div class="xc-card">
              <p class="xc-section-title" style="margin-top:0">Context</p>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.85rem">
                <div style="color:var(--text-muted)">Account equity</div>
                <div style="text-align:right"><b>{eq_str}</b></div>
                <div style="color:var(--text-muted)">HTF bias</div>
                <div style="text-align:right"><b>{sig.htf_bias}</b></div>
                <div style="color:var(--text-muted)">Session</div>
                <div style="text-align:right"><b>{sig.session or '—'}</b></div>
                <div style="color:var(--text-muted)">Last close</div>
                <div style="text-align:right">
                  <b>{(sig.metadata or {}).get('last_close', 0):.2f}</b>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_history() -> None:
    if not SIGNAL_LOG.exists():
        st.markdown(
            "<div class='xc-card-flat' style='text-align:center;color:var(--text-muted);"
            "padding:18px'>No signal log file yet.</div>",
            unsafe_allow_html=True,
        )
        return
    rows = []
    for line in SIGNAL_LOG.read_text(encoding="utf-8").splitlines()[-200:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    if not rows:
        st.markdown(
            "<div class='xc-card-flat' style='text-align:center;color:var(--text-muted);"
            "padding:18px'>No signals logged yet.</div>",
            unsafe_allow_html=True,
        )
        return
    df = pd.DataFrame(rows).sort_values("ts", ascending=False)
    df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce").dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    show = df[["time", "direction", "confidence", "entry", "sl", "tp", "rr", "htf_bias"]].head(
        50
    ).rename(columns={
        "time": "Time", "direction": "Direction", "confidence": "Conf %",
        "entry": "Entry", "sl": "SL", "tp": "TP", "rr": "R:R", "htf_bias": "Bias",
    })
    st.dataframe(show, width="stretch", hide_index=True)


def render() -> None:
    symbol = st.session_state.get("symbol", "XAUUSD")
    cfg = st.session_state.get("cfg", {}).get("strategy", {})
    htf = cfg.get("higher_timeframe", "H4")
    ltf = cfg.get("entry_timeframe", "M15")
    mode = st.session_state.get("strategy_mode", "swing")

    if mode == "scalp":
        htf = cfg.get("scalp_higher_timeframe", htf)
        ltf = cfg.get("scalp_entry_timeframe", ltf)

    st.markdown('<p class="xc-section-title">Current Signal</p>', unsafe_allow_html=True)
    try:
        df_ltf = fetch_bars(symbol, ltf, 300)
        df_htf = fetch_bars(symbol, htf, 300) if htf else None
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to load bars: {e}")
        return
    if df_ltf is None or df_ltf.empty:
        st.warning("No LTF data.")
        return

    sig = get_strategy(mode, strategy_name=st.session_state.get("active_strategy")).generate_signal(df_ltf, df_htf=df_htf, symbol=symbol)
    try:
        account = fetch_account()
        info = fetch_symbol_info(symbol)
    except Exception:
        account, info = None, None
    _render_current(sig, account, info, strategy_name=st.session_state.get("active_strategy"))

    st.markdown('<p class="xc-section-title">Signal History</p>', unsafe_allow_html=True)
    _render_history()
