"""Streamlit dashboard — main entry point.

Run with:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from streamlit_autorefresh import st_autorefresh  # noqa: E402

from dashboard.styles import inject_global_styles  # noqa: E402
from utils.config import get_config  # noqa: E402

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="AURIC — XAUUSD Bot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_global_styles()

# ── Constants ────────────────────────────────────────────────────────
SIDEBAR_W = 200

NAV_MAIN = [
    ("Overview",       "squares-four"),
    ("Live Chart",     "chart-line"),
    ("Signals",        "lightning"),
    ("Trades",         "arrows-left-right"),
    ("Performance",    "chart-bar"),
    ("Backtest",       "clock-counter-clockwise"),
    ("Strategy Maker", "cpu"),
]
NAV_BOTTOM = [
    ("Settings", "gear"),
    ("Logs",     "terminal"),
]

# ── Read query params ────────────────────────────────────────────────
qp = st.query_params
current_page = qp.get("page", "Overview")
current_mode = qp.get("mode", "swing")

# ── Initialize session state ────────────────────────────────────────
cfg = get_config()
st.session_state.setdefault("cfg", cfg)
st.session_state.setdefault("symbol", cfg.get("app", {}).get("symbol", "XAUUSD-VIP"))
st.session_state.setdefault("auto_refresh", True)
st.session_state.setdefault("refresh_interval", 15)

# Sync mode from query param
st.session_state["strategy_mode"] = current_mode

# Active strategy — read from query param or fallback to config
active_strategy = qp.get("strategy", cfg.get("strategy", {}).get("active_strategy", "luxalgo_smc"))
st.session_state["active_strategy"] = active_strategy

if st.session_state.get("auto_refresh", True):
    interval = st.session_state.get("refresh_interval", 15) * 1000
    st_autorefresh(interval=interval, key="global_refresh")

# ── Build sidebar HTML ──────────────────────────────────────────────
def _sidebar_html() -> str:
    d = []
    d.append(
        f'<div class="auric-sidebar" style="'
        f'display:flex;flex-direction:column;'
        f'padding:16px 10px;'
        f'width:{SIDEBAR_W}px;'
        f'min-height:100vh;'
        f'background:#0d1117;'
        f'border-right:0.5px solid #21262d;'
        f'position:fixed;top:0;left:0;z-index:100;'
        f'overflow-y:auto;overflow-x:hidden'
        f'">'
    )

    # ── Logo + brand
    d.append(
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:20px;padding:0 6px">'
        '<div style="width:30px;height:30px;border-radius:7px;background:#2d2208;'
        'display:flex;align-items:center;justify-content:center;font-size:13px;'
        'font-weight:500;color:#d29922;flex-shrink:0">A</div>'
        '<span style="font-size:13px;font-weight:600;color:#e6edf3;letter-spacing:.03em">'
        'AURIC</span></div>'
    )

    # ── Main nav links
    for label, icon in NAV_MAIN:
        active = current_page == label
        bg = '#2d2208' if active else 'transparent'
        clr = '#d29922' if active else '#8b949e'
        weight = '500' if active else '400'
        d.append(
            f'<a href="?page={label}&mode={current_mode}&strategy={active_strategy}" '
            f'target="_parent" '
            f'style="display:flex;align-items:center;gap:8px;width:100%;'
            f'padding:7px 8px;margin:1px 0;border-radius:6px;'
            f'background:{bg};color:{clr};font-size:12px;font-weight:{weight};'
            f'text-decoration:none;transition:background .15s">'
            f'<i class="ph ph-{icon}" style="font-size:15px;flex-shrink:0;width:18px;text-align:center"></i>'
            f'<span>{label}</span></a>'
        )

    # ── Spacer
    d.append('<div style="flex:1;min-height:20px"></div>')

    # ── Bottom nav
    for label, icon in NAV_BOTTOM:
        active = current_page == label
        bg = '#2d2208' if active else 'transparent'
        clr = '#d29922' if active else '#8b949e'
        d.append(
            f'<a href="?page={label}&mode={current_mode}&strategy={active_strategy}" '
            f'target="_parent" '
            f'style="display:flex;align-items:center;gap:8px;width:100%;'
            f'padding:7px 8px;margin:1px 0;border-radius:6px;'
            f'background:{bg};color:{clr};font-size:12px;'
            f'text-decoration:none">'
            f'<i class="ph ph-{icon}" style="font-size:15px;flex-shrink:0;width:18px;text-align:center"></i>'
            f'<span>{label}</span></a>'
        )

    # ── Mode toggle (SWING / SCALP)
    d.append(
        '<div style="border-top:0.5px solid #21262d;padding-top:10px;margin-top:10px">'
        '<div style="font-size:9px;color:#6e7681;text-transform:uppercase;'
        'letter-spacing:.06em;margin-bottom:6px;padding:0 8px">Mode</div>'
        '<div style="display:flex;gap:4px;padding:0 8px">'
    )
    for m in ("swing", "scalp"):
        is_active = m == current_mode
        bg = '#d29922' if is_active else '#161b22'
        clr = '#0d1117' if is_active else '#6e7681'
        fw = '600' if is_active else '400'
        d.append(
            f'<a href="?page={current_page}&mode={m}&strategy={active_strategy}" '
            f'target="_parent" '
            f'style="flex:1;text-align:center;padding:5px 0;border-radius:5px;'
            f'background:{bg};color:{clr};font-size:10px;font-weight:{fw};'
            f'text-decoration:none;border:0.5px solid {"#d29922" if is_active else "#21262d"}">'
            f'{m.upper()}</a>'
        )
    d.append('</div></div>')

    # ── Active strategy label
    strategy_short = active_strategy.replace("_", " ").title()
    if len(strategy_short) > 18:
        strategy_short = strategy_short[:16] + "…"
    d.append(
        f'<div style="border-top:0.5px solid #21262d;padding-top:10px;margin-top:10px">'
        f'<div style="font-size:9px;color:#6e7681;text-transform:uppercase;'
        f'letter-spacing:.06em;margin-bottom:4px;padding:0 8px">Strategy</div>'
        f'<div style="padding:5px 8px;font-size:11px;color:#d29922;font-weight:500;'
        f'background:#2d2208;border-radius:5px;margin:0 8px;text-align:center">'
        f'{strategy_short}</div>'
        f'</div>'
    )

    d.append('</div>')
    return "".join(d)


# ── Render sidebar ───────────────────────────────────────────────────
st.markdown(_sidebar_html(), unsafe_allow_html=True)

# ── Strategy selector (inline, not in columns) ──────────────────────
from strategy import list_strategies  # noqa: E402

_strategies = list_strategies()
_strategy_names = [s["name"] for s in _strategies] if _strategies else ["luxalgo_smc"]

try:
    _idx = _strategy_names.index(active_strategy)
except ValueError:
    _idx = 0

_sel = st.selectbox(
    "Strategy",
    options=_strategy_names,
    format_func=lambda n: next(
        (s.get("label", s["name"]) for s in _strategies if s["name"] == n), n
    ),
    index=_idx,
    key="_strategy_select",
    label_visibility="collapsed",
    width="content",
)
if _sel != active_strategy:
    st.query_params.update(strategy=_sel, page=current_page, mode=current_mode)
    st.rerun()

# ── Route to view ────────────────────────────────────────────────────
from dashboard.views import (  # noqa: E402
    home, live_chart, signals, trades,
    performance, backtest, strategy_maker, settings, logs,
)

PAGE_MAP = {
    "Overview":       home.render,
    "Live Chart":     live_chart.render,
    "Signals":        signals.render,
    "Trades":         trades.render,
    "Performance":    performance.render,
    "Backtest":       backtest.render,
    "Strategy Maker": strategy_maker.render,
    "Settings":       settings.render,
    "Logs":           logs.render,
}

PAGE_MAP.get(current_page, home.render)()
