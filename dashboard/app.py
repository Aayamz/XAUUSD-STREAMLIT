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
    initial_sidebar_state="expanded",
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

# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    # Logo
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;
         padding:12px 0 14px">
      <div style="width:34px;height:34px;border-radius:9px;background:#2d2208;
           display:flex;align-items:center;justify-content:center;
           font-size:14px;font-weight:500;color:#d29922">A</div>
    </div>""", unsafe_allow_html=True)

    # Main nav items
    for label, icon in NAV_MAIN:
        active = current_page == label
        st.markdown(f"""
        <a href="?page={label}" title="{label}" style="
            display:flex;align-items:center;justify-content:center;
            width:40px;height:40px;margin:2px auto;border-radius:8px;
            background:{'#2d2208' if active else 'transparent'};
            color:{'#d29922' if active else '#6e7681'};
            font-size:19px;text-decoration:none;">
          <i class="ph ph-{icon}"></i>
        </a>""", unsafe_allow_html=True)

    # Spacer pushes bottom items down
    st.markdown('<div style="height:40px"></div>', unsafe_allow_html=True)

    # Bottom nav items
    for label, icon in NAV_BOTTOM:
        active = current_page == label
        st.markdown(f"""
        <a href="?page={label}" title="{label}" style="
            display:flex;align-items:center;justify-content:center;
            width:40px;height:40px;margin:2px auto;border-radius:8px;
            background:{'#2d2208' if active else 'transparent'};
            color:{'#d29922' if active else '#6e7681'};
            font-size:19px;text-decoration:none;">
          <i class="ph ph-{icon}"></i>
        </a>""", unsafe_allow_html=True)

    # Mode badge at the very bottom
    mode = st.session_state.get("strategy_mode", "swing").upper()
    st.markdown(f"""
    <div style="border-top:0.5px solid #21262d;padding-top:10px;
         margin-top:8px;text-align:center">
      <div style="font-size:9px;color:#6e7681;text-transform:uppercase;
           letter-spacing:.05em;margin-bottom:4px">Mode</div>
      <div style="padding:2px 0;background:#2d2208;border-radius:4px;
           font-size:9px;font-weight:500;color:#d29922">{mode}</div>
    </div>""", unsafe_allow_html=True)

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
