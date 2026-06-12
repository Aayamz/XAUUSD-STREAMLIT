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

# ── Page config — must be the very first Streamlit call ─────────────
st.set_page_config(
    page_title="AURIC — XAUUSD Bot",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global styles injected once here; each view also calls it ────────
inject_global_styles()

# ── URL-based routing ────────────────────────────────────────────────
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

current_page = st.query_params.get("page", "Overview")

# ── Initialize session state ────────────────────────────────────────
cfg = get_config()
st.session_state.setdefault("cfg", cfg)
st.session_state.setdefault("symbol", cfg.get("app", {}).get("symbol", "XAUUSD-VIP"))
st.session_state.setdefault("strategy_mode", "swing")
st.session_state.setdefault("active_strategy", cfg.get("strategy", {}).get("active_strategy", "luxalgo_smc"))
st.session_state.setdefault("auto_refresh", True)
st.session_state.setdefault("refresh_interval", 15)

if st.session_state.get("auto_refresh", True):
    interval = st.session_state.get("refresh_interval", 15) * 1000
    st_autorefresh(interval=interval, key="global_refresh")

# ── Build nav HTML ──────────────────────────────────────────────────
def _nav_html() -> str:
    html = '<div style="display:flex;flex-direction:column;align-items:center;padding:12px 0;width:56px;min-height:100vh;background:#0d1117;border-right:0.5px solid #21262d;position:fixed;top:0;left:0;z-index:100">'
    # Logo
    html += '<div style="width:34px;height:34px;border-radius:9px;background:#2d2208;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:500;color:#d29922;margin-bottom:16px">A</div>'
    # Main nav
    for label, icon in NAV_MAIN:
        active = current_page == label
        bg = '#2d2208' if active else 'transparent'
        clr = '#d29922' if active else '#6e7681'
        html += f'<a href="?page={label}" title="{label}" style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;margin:2px 0;border-radius:8px;background:{bg};color:{clr};font-size:18px;text-decoration:none"><i class="ph ph-{icon}"></i></a>'
    # Spacer
    html += '<div style="flex:1"></div>'
    # Bottom nav
    for label, icon in NAV_BOTTOM:
        active = current_page == label
        bg = '#2d2208' if active else 'transparent'
        clr = '#d29922' if active else '#6e7681'
        html += f'<a href="?page={label}" title="{label}" style="display:flex;align-items:center;justify-content:center;width:40px;height:40px;margin:2px 0;border-radius:8px;background:{bg};color:{clr};font-size:18px;text-decoration:none"><i class="ph ph-{icon}"></i></a>'
    # Mode badge
    mode = st.session_state.get("strategy_mode", "swing").upper()
    html += f'<div style="border-top:0.5px solid #21262d;padding-top:8px;margin-top:8px;text-align:center;width:40px"><div style="font-size:8px;color:#6e7681;text-transform:uppercase;letter-spacing:.05em">Mode</div><div style="padding:2px 0;background:#2d2208;border-radius:4px;font-size:9px;font-weight:500;color:#d29922;margin-top:4px">{mode}</div></div>'
    html += '</div>'
    return html

# ── Render layout: fixed nav rail + main content ────────────────────
nav_html = _nav_html()
st.markdown(nav_html, unsafe_allow_html=True)

# Offset main content to the right of the fixed nav rail
st.markdown('<style>.block-container{margin-left:56px;padding-left:1rem;padding-right:1rem;box-sizing:border-box}</style>', unsafe_allow_html=True)

# ── Strategy mode header (rendered after nav to align with view) ──────────────────────────────────────────────
st.markdown('<div class="tb-section-label" style="margin-top:16px;margin-left:56px">Strategy Mode</div>', unsafe_allow_html=True)
current_mode = st.session_state.get("strategy_mode", "swing")
mode_radio = st.radio("", options=["swing", "scalp"], index=["swing", "scalp"].index(current_mode),
                      horizontal=True, key="mode_radio", label_visibility="collapsed")
if mode_radio != current_mode:
    st.session_state["strategy_mode"] = mode_radio
    st.rerun()

# ── Route to the correct view ────────────────────────────────────────
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
