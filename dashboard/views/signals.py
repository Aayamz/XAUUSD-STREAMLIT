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
from utils.config import PROJECT_ROOT


SIGNAL_LOG = PROJECT_ROOT / "logs" / "signals.jsonl"


def _render_current(sig, account, info, strategy_name: str | None = None) -> None:
    direction = sig.direction.value
    conf = float(sig.confidence)
    entry = sig.entry
    sl = sig.stop_loss
    tp = sig.take_profit
    rr = sig.rr
    reasons = sig.reasons

    strategy_label = next(
        (s["label"] for s in list_strategies() if s["name"] == strategy_name),
        strategy_name or "—",
    )

    circumference = 226.19
    offset = round(circumference * (1 - conf / 100), 2)
    dir_color = "#f85149" if direction == "SHORT" else "#3fb950"
    arc_color = "#d29922"
    risk_pts = round(abs(entry - sl), 2) if entry and sl else 0
    reward_pts = round(abs(tp - entry), 2) if tp and entry else 0

    reasons_html = ""
    for r in reasons:
        reasons_html += '<span class="tb-tag">' + r + '</span> '

    # Build the SVG ring
    svg_html = (
        '<svg width="96" height="96" viewBox="0 0 96 96">'
        '<circle cx="48" cy="48" r="36" fill="none" stroke="#21262d" stroke-width="7"/>'
        '<circle cx="48" cy="48" r="36" fill="none" stroke="' + arc_color + '" stroke-width="7"'
        ' stroke-dasharray="' + str(circumference) + '"'
        ' stroke-dashoffset="' + str(offset) + '"'
        ' stroke-linecap="round" transform="rotate(-90 48 48)"/>'
        '<text x="48" y="44" text-anchor="middle" font-size="10" font-weight="500"'
        ' style="fill:' + dir_color + ';font-family:Inter,sans-serif">' + direction + '</text>'
        '<text x="48" y="62" text-anchor="middle" font-size="19" font-weight="500"'
        ' style="fill:' + arc_color + ";font-family:'JetBrains Mono',monospace\">" + f"{conf:.0f}" + '%</text>'
        '</svg>'
    )

    card_html = (
        '<div class="tb-card" style="margin-bottom:8px">'
        '<div style="display:flex;gap:16px;align-items:flex-start">'
        '<div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0">'
        + svg_html +
        '<div style="font-size:10px;color:#6e7681;text-transform:uppercase;letter-spacing:.07em;margin-top:-4px">Confidence</div>'
        '</div>'
        '<div style="flex:1;min-width:0">'
        '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px">'
        '<div><div class="tb-label">Entry</div><div class="tb-value-sm">' + f"{entry:,.2f}" + '</div></div>'
        '<div><div class="tb-label">Stop loss</div><div class="tb-value-sm tb-value-danger">' + f"{sl:,.2f}" + '</div></div>'
        '<div><div class="tb-label">Take profit</div><div class="tb-value-sm tb-value-success">' + f"{tp:,.2f}" + '</div></div>'
        '<div><div class="tb-label">R:R ratio</div><div class="tb-value-sm">' + f"{rr:.2f}" + '</div></div>'
        '</div>'
        '<div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;align-items:center">'
        '<span style="font-size:10px;color:#6e7681;margin-right:2px">Reasons:</span> '
        + reasons_html +
        '</div>'
        '<div style="display:flex;align-items:center;gap:8px">'
        '<span style="font-size:11px;color:#6e7681">' + strategy_label + '</span>'
        '</div>'
        '</div>'
        '</div>'
        '<div style="border-top:0.5px solid #21262d;margin-top:12px;padding-top:10px;display:flex;align-items:center;gap:16px">'
        '<span style="font-size:12px;color:#6e7681">Risk <span style="color:#f85149;font-family:\'JetBrains Mono\',monospace;font-weight:500">' + str(risk_pts) + ' pts</span></span>'
        '<span style="font-size:12px;color:#6e7681">Reward <span style="color:#3fb950;font-family:\'JetBrains Mono\',monospace;font-weight:500">' + str(reward_pts) + ' pts</span></span>'
        '<span style="font-size:12px;color:#6e7681">R:R <span style="color:#e6edf3;font-family:\'JetBrains Mono\',monospace;font-weight:500">' + f"{rr:.2f}" + '</span></span>'
        '</div>'
        '</div>'
    )

    st.markdown(card_html, unsafe_allow_html=True)


def _render_history() -> None:
    if not SIGNAL_LOG.exists():
        st.markdown(
            "<div style='text-align:center;color:#6e7681;padding:18px;font-size:12px'>"
            "No signal log file yet.</div>",
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
            "<div style='text-align:center;color:#6e7681;padding:18px;font-size:12px'>"
            "No signals logged yet.</div>",
            unsafe_allow_html=True,
        )
        return

    df = pd.DataFrame(rows).sort_values("ts", ascending=False).head(50)
    df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce").dt.strftime(
        "%H:%M:%S"
    )

    st.markdown('<div class="tb-section-label" style="margin-top:16px">Signal history</div>',
                unsafe_allow_html=True)

    rows_html = ""
    for _, sig in df.iterrows():
        d = sig.get("direction", "—")
        dir_class = "tb-pill-short" if d == "SHORT" else "tb-pill-long"
        conf_val = sig.get("confidence", "—")
        entry_val = sig.get("entry", 0)
        sl_val = sig.get("sl", 0)
        tp_val = sig.get("tp", 0)
        rr_val = sig.get("rr", "—")
        bias_val = sig.get("htf_bias", "—")
        ts_val = sig.get("time", "—")

        rows_html += (
            '<tr>'
            '<td>' + str(ts_val) + '</td>'
            '<td><span class="tb-pill ' + dir_class + '" style="font-size:11px">' + str(d) + '</span></td>'
            '<td>' + str(conf_val) + '%</td>'
            '<td>' + f"{entry_val:,.2f}" + '</td>'
            '<td style="color:#f85149">' + f"{sl_val:,.2f}" + '</td>'
            '<td style="color:#3fb950">' + f"{tp_val:,.2f}" + '</td>'
            '<td>' + str(rr_val) + '</td>'
            '<td style="color:#6e7681">' + str(bias_val) + '</td>'
            '</tr>'
        )

    table_html = (
        '<div style="overflow-x:auto">'
        '<table class="tb-signal-table">'
        '<thead><tr>'
        '<th>Time</th><th>Direction</th><th>Conf %</th>'
        '<th>Entry</th><th>SL</th><th>TP</th><th>R:R</th><th>Bias</th>'
        '</tr></thead>'
        '<tbody>' + rows_html + '</tbody>'
        '</table></div>'
    )

    st.markdown(table_html, unsafe_allow_html=True)


def render() -> None:
    symbol = st.session_state.get("symbol", "XAUUSD")
    cfg = st.session_state.get("cfg", {}).get("strategy", {})
    htf = cfg.get("higher_timeframe", "H4")
    ltf = cfg.get("entry_timeframe", "M15")
    mode = st.session_state.get("strategy_mode", "swing")

    if mode == "scalp":
        htf = cfg.get("scalp_higher_timeframe", htf)
        ltf = cfg.get("scalp_entry_timeframe", ltf)

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

    st.markdown('<div class="tb-section-label">Current Signal</div>', unsafe_allow_html=True)
    _render_current(sig, account, info, strategy_name=st.session_state.get("active_strategy"))

    _render_history()
