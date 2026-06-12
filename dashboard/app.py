"""Streamlit dashboard — main entry point.

Run with:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from streamlit_autorefresh import st_autorefresh  # noqa: E402

from dashboard.state import get_bot_runner, get_client  # noqa: E402
from dashboard.styles import inject_global_styles  # noqa: E402
from strategy import available_strategies_for_mode, get_strategy_info  # noqa: E402
from utils.config import get_config, get_trading_mode  # noqa: E402

PAGES = [
    "Overview", "Live Chart", "Signals", "Trades", "Performance",
    "Backtest", "Strategy Maker", "Settings", "Logs",
]
PAGE_ICONS = {
    "Overview": "📊", "Live Chart": "📈", "Signals": "⚡",
    "Trades": "💱", "Performance": "📋", "Backtest": "⏪",
    "Strategy Maker": "🤖", "Settings": "⚙️", "Logs": "📝",
}


def _setup() -> None:
    st.set_page_config(
        page_title="AURIC — XAUUSD Trading Bot",
        page_icon="🟡",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_global_styles()
    cfg = get_config()
    st.session_state.setdefault("cfg", cfg)
    st.session_state.setdefault("symbol", cfg.get("app", {}).get("symbol", "XAUUSD-VIP"))
    st.session_state.setdefault("mode", get_trading_mode())
    st.session_state.setdefault("strategy_mode", "swing")
    st.session_state.setdefault("active_strategy", cfg.get("strategy", {}).get("active_strategy", "luxalgo_smc"))
    st.session_state.setdefault("auto_refresh", True)
    st.session_state.setdefault("refresh_interval", 15)
    st.session_state.setdefault("current_page", "Overview")

    if st.session_state.get("auto_refresh", True):
        interval = st.session_state.get("refresh_interval", 15) * 1000
        st_autorefresh(interval=interval, key="global_refresh")


def _render_appbar() -> None:
    client = get_client()
    is_mock = client.name == "mock" if hasattr(client, "name") else False
    symbol = st.session_state.get("symbol", "XAUUSD")
    strategy_mode = st.session_state.get("strategy_mode", "swing").upper()
    runner = get_bot_runner()
    auto = runner.is_running()

    st.markdown(f"""
<div class="xc-appbar">
  <div class="brand">
    <div class="logo">A</div>
    <span>AURIC</span>
    <span class="xc-badge xc-badge-accent" style="margin-left:6px">{strategy_mode}</span>
  </div>
  <div class="meta">
    <span><b>{symbol}</b></span>
    <span class="xc-badge {'xc-badge-mock' if is_mock else 'xc-badge-live'}">{'🟡 SIM' if is_mock else '🟢 LIVE'}</span>
    <span class="xc-badge {'xc-badge-on' if auto else 'xc-badge-off'}">
      <span class="xc-dot" style="opacity:{'1' if auto else '0.3'}"></span>
      {'AUTO' if auto else 'OFF'}
    </span>
  </div>
</div>
""", unsafe_allow_html=True)


def _render_sidebar_content() -> None:
    """Render sidebar UI inside a column (not st.sidebar)."""
    cfg = get_config()
    client = get_client()
    runner = get_bot_runner()

    # ---- Brand ----------------------------------------------------------
    st.markdown("""
<div class="sb-brand">
  <div class="sb-brand-logo">A</div>
  <div>
    <div class="sb-brand-text">AURIC</div>
    <div class="sb-brand-sub">v1.0.0</div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ---- Auto-trading toggle --------------------------------------------
    was_running = runner.is_running()
    auto = st.toggle("Auto-Trading", value=was_running,
                     help="Run the strategy loop in the background.",
                     key="auto_trade_toggle")

    if auto and not was_running:
        strat_name = st.session_state.get("active_strategy", "luxalgo_smc")
        strat_mode = st.session_state.get("strategy_mode", "swing")
        strat_info = get_strategy_info(strat_name)
        strat_label = strat_info["label"] if strat_info else strat_name
        with st.popover("Confirm", width="stretch"):
            st.markdown(f"**{strat_label}** · `{strat_mode.upper()}`")
            c1, c2 = st.columns(2)
            if c1.button("Cancel", width="stretch"):
                st.session_state.auto_trade_toggle = False
                st.rerun()
            if c2.button("Start", type="primary", width="stretch"):
                ok = runner.start(interval=int(cfg.get("app", {}).get("refresh_seconds", 60)))
                st.toast("Started" if ok else f"Failed: {runner.status().get('last_error')}", icon="🟢" if ok else "❌")
                st.rerun()
    elif (not auto) and was_running:
        runner.stop()
        st.toast("Stopped", icon="🔴")
        st.rerun()

    if auto:
        status = runner.status()
        iv = status.get("interval", 60)
        new_iv = st.slider("Tick (s)", 10, 600, iv, step=5, key="auto_interval")
        if new_iv != iv:
            runner.set_interval(new_iv)
        c1, c2 = st.columns(2)
        c1.metric("Ticks", status.get("ticks_run", 0))
        c2.metric("Trades", status.get("trades_opened", 0))
        err = status.get("last_error")
        if err:
            st.error(f"Error: {err}")

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    # ---- Navigation -----------------------------------------------------
    current_page = st.session_state.get("current_page", "Overview")
    page_index = PAGES.index(current_page) if current_page in PAGES else 0

    # Hidden radio for state management
    selected = st.radio("nav", PAGES, index=page_index, key="nav_radio", label_visibility="collapsed")
    if selected != current_page:
        st.session_state.current_page = selected
        st.rerun()

    # Visual nav items
    nav_html = '<div style="margin-top:4px">'
    for page in PAGES:
        icon = PAGE_ICONS.get(page, "•")
        active = " active" if page == current_page else ""
        nav_html += f'<div class="sb-nav-item{active}"><span class="sb-nav-icon">{icon}</span>{page}</div>'
    nav_html += '</div>'
    st.markdown(nav_html, unsafe_allow_html=True)

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    # ---- Strategy mode --------------------------------------------------
    st.markdown('<div class="sb-section">Strategy Mode</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, m in enumerate(["swing", "scalp"]):
        active = st.session_state.get("strategy_mode", "swing") == m
        label = ("● " if active else "") + m.upper()
        if cols[i].button(label, key=f"mode_{m}", width="stretch",
                          type="primary" if active else "secondary"):
            st.session_state.strategy_mode = m
            st.rerun()

    # ---- Strategy selector ----------------------------------------------
    mode = st.session_state.get("strategy_mode", "swing")
    scalp_strats = available_strategies_for_mode(mode)
    if len(scalp_strats) > 1:
        st.markdown('<div class="sb-section">Strategy</div>', unsafe_allow_html=True)
        strat_names = [s["name"] for s in scalp_strats]
        current = st.session_state.get("active_strategy", "luxalgo_smc")
        try:
            idx = strat_names.index(current)
        except ValueError:
            idx = 0
        sel = st.selectbox("strat", strat_names,
                           format_func=lambda n: next((s["label"] for s in scalp_strats if s["name"] == n), n),
                           index=idx, key="strategy_select", label_visibility="collapsed")
        if sel != current:
            st.session_state.active_strategy = sel
            st.rerun()
    elif scalp_strats:
        st.session_state.active_strategy = scalp_strats[0]["name"]

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    # ---- Auto-refresh ---------------------------------------------------
    st.markdown('<div class="sb-section">Live Data</div>', unsafe_allow_html=True)
    auto_refresh = st.toggle("Auto-refresh", value=st.session_state.get("auto_refresh", True), key="auto_refresh_toggle")
    st.session_state.auto_refresh = auto_refresh
    if auto_refresh:
        refresh_iv = st.slider("Interval (s)", 5, 60, st.session_state.get("refresh_interval", 15), step=5, key="refresh_interval_slider")
        st.session_state.refresh_interval = refresh_iv

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    # ---- Status ---------------------------------------------------------
    connected = client.is_connected()
    dot_color = "#2ecc71" if connected else "#ef5350"
    status_text = "connected" if connected else "offline"
    st.markdown(f"""
<div class="sb-status">
  MT5: <b style="color:{dot_color}">● {status_text}</b><br>
  Symbol: <b style="color:#e8eaed">{st.session_state.get("symbol", "XAUUSD")}</b><br>
  Time: <b style="color:#e8eaed">{time.strftime("%H:%M:%S UTC", time.gmtime())}</b>
</div>
""", unsafe_allow_html=True)


def _render_page(page: str) -> None:
    if page == "Overview":
        from dashboard.views import home
        home.render()
    elif page == "Live Chart":
        from dashboard.views import live_chart
        live_chart.render()
    elif page == "Signals":
        from dashboard.views import signals
        signals.render()
    elif page == "Trades":
        from dashboard.views import trades
        trades.render()
    elif page == "Performance":
        from dashboard.views import performance
        performance.render()
    elif page == "Backtest":
        from dashboard.views import backtest
        backtest.render()
    elif page == "Strategy Maker":
        from dashboard.views import strategy_maker
        strategy_maker.render()
    elif page == "Settings":
        from dashboard.views import settings
        settings.render()
    elif page == "Logs":
        from dashboard.views import logs
        logs.render()


def main() -> None:
    _setup()
    _render_appbar()

    current_page = st.session_state.get("current_page", "Overview")

    # Custom sidebar + main content via columns
    sidebar_col, main_col = st.columns([1, 4], gap="small")

    with sidebar_col:
        _render_sidebar_content()

    with main_col:
        _render_page(current_page)


if __name__ == "__main__":
    main()
