"""Streamlit dashboard — main entry point.

Run with:
    streamlit run dashboard/app.py

Architecture:
    - One Streamlit session per browser tab
    - ``st.cache_resource`` keeps the MT5 client, fetcher, strategy, and
      BotRunner as singletons across reruns
    - Auto-trading runs in a background thread controlled by the sidebar
      toggle — no need to run ``main.py`` separately
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from streamlit_option_menu import option_menu  # noqa: E402
from streamlit_autorefresh import st_autorefresh  # noqa: E402

from dashboard.state import (  # noqa: E402
    get_bot_runner, get_client,
)
from dashboard.styles import inject_global_styles  # noqa: E402
from strategy import available_strategies_for_mode, get_strategy_info  # noqa: E402
from utils.config import get_config, get_trading_mode  # noqa: E402


PAGES = {
    "Overview":       "squares-four",
    "Live Chart":     "chart-line",
    "Signals":        "lightning",
    "Trades":         "arrows-left-right",
    "Performance":    "chart-bar",
    "Backtest":       "clock-counter-clockwise",
    "Strategy Maker": "cpu",
    "Settings":       "gear",
    "Logs":           "terminal",
}


# --- App bar (top header) -----------------------------------------------------
def _render_appbar() -> None:
    client = get_client()
    is_mock = client.name == "mock" if hasattr(client, "name") else False

    symbol = st.session_state.get("symbol", "XAUUSD")
    strategy_mode = st.session_state.get("strategy_mode", "swing").upper()

    runner = get_bot_runner()
    auto = runner.is_running()

    st.markdown(
        f"""
        <div class="xc-appbar">
          <div class="brand">
            <div class="logo">A</div>
            <span>AURIC</span>
            <span class="xc-badge xc-badge-accent" style="margin-left:6px">{strategy_mode}</span>
          </div>
          <div class="meta">
            <span><b>{symbol}</b></span>
            <span class="xc-badge {'xc-badge-mock' if is_mock else 'xc-badge-live'}">
              {'🟡 SIMULATED' if is_mock else '🟢 LIVE'}
            </span>
            <span class="xc-badge {'xc-badge-on' if auto else 'xc-badge-off'}">
              <span class="xc-dot" style="opacity:{'1' if auto else '0.3'}"></span>
              {'AUTO-TRADING ON' if auto else 'AUTO-TRADING OFF'}
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- Sidebar (navigation + controls) ------------------------------------------
def _sidebar() -> str:
    cfg = get_config()
    client = get_client()

    with st.sidebar:
        # ---- Brand header ---------------------------------------------------
        st.markdown(
            """
            <div style="text-align:center;padding:8px 0 16px 0">
              <div style="display:inline-flex;align-items:center;gap:8px">
                <div style="width:36px;height:36px;border-radius:10px;
                            background:linear-gradient(135deg,#f0b90b 0%,#b88800 100%);
                            display:flex;align-items:center;justify-content:center;
                            color:#0a0e1a;font-weight:800;font-size:1.1rem;
                            box-shadow:0 2px 8px rgba(240,185,11,0.35)">A</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ---- Auto-trading toggle (prominent) --------------------------------
        runner = get_bot_runner()
        was_running = runner.is_running()
        auto = st.toggle(
            "Auto-Trading",
            value=was_running,
            help="Run the strategy loop in the background.",
            key="auto_trade_toggle",
        )

        if auto and not was_running:
            strat_name = st.session_state.get("active_strategy", "luxalgo_smc")
            strat_mode = st.session_state.get("strategy_mode", "swing")
            strat_info = get_strategy_info(strat_name)
            strat_label = strat_info["label"] if strat_info else strat_name

            with st.popover("Confirm Strategy", width="stretch"):
                st.markdown(f"""
                **Strategy:** `{strat_label}`  
                **Mode:** `{strat_mode.upper()}`  
                **ID:** `{strat_name}`
                """, unsafe_allow_html=False)
                col_c1, col_c2 = st.columns(2)
                if col_c1.button("Cancel", width="stretch"):
                    st.session_state.auto_trade_toggle = False
                    st.rerun()
                if col_c2.button("Confirm & Start", type="primary", width="stretch"):
                    ok = runner.start(interval=int(cfg.get("app", {}).get("refresh_seconds", 60)))
                    if ok:
                        st.toast("Auto-trading started", icon="🟢")
                    else:
                        err = runner.status().get("last_error") or "unknown"
                        st.toast(f"Failed to start: {err}", icon="❌")
                    st.rerun()
        elif (not auto) and was_running:
            runner.stop()
            st.toast("Auto-trading stopped", icon="🔴")
            st.rerun()

        if auto:
            status = runner.status()
            iv = status.get("interval", 60)
            new_iv = st.slider("Tick interval (s)", 10, 600, iv, step=5,
                               key="auto_interval",
                               help="How often the strategy evaluates a new signal")
            if new_iv != iv:
                runner.set_interval(new_iv)
            col_a, col_b = st.columns(2)
            col_a.metric("Ticks", status.get("ticks_run", 0))
            col_b.metric("Trades", status.get("trades_opened", 0))
            err = status.get("last_error")
            if err:
                st.error(f"Last error: {err}")

        st.divider()

        # ---- Navigation (Phosphor icons) ------------------------------------
        icons = [PAGES[k] for k in PAGES]
        choice = option_menu(
            None,
            list(PAGES.keys()),
            icons=icons,
            menu_icon=None,
            default_index=0,
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "icon": {"color": "#f0b90b", "font-size": "16px"},
                "nav-link": {
                    "font-size": "13px",
                    "margin": "2px 0",
                    "color": "#a8b0bf",
                    "border-radius": "8px",
                },
                "nav-link-selected": {
                    "background-color": "rgba(240,185,11,0.08)",
                    "color": "#f0b90b",
                    "border-left": "3px solid #f0b90b",
                },
            },
        )

        st.divider()

        # ---- Strategy mode --------------------------------------------------
        st.markdown(
            "<p style='color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;"
            "letter-spacing:0.1em;margin:0 0 6px 0'>Strategy Mode</p>",
            unsafe_allow_html=True,
        )
        cols = st.columns(2)
        for i, m in enumerate(["swing", "scalp"]):
            active = st.session_state.get("strategy_mode", "swing") == m
            label = ("🟢 " if active else "") + m.upper()
            if cols[i].button(label, key=f"mode_{m}", width="stretch",
                              type="primary" if active else "secondary"):
                st.session_state.strategy_mode = m
                st.rerun()

        # ---- Strategy selector (for scalp mode) -----------------------------
        mode = st.session_state.get("strategy_mode", "swing")
        scalp_strats = available_strategies_for_mode(mode)
        if len(scalp_strats) > 1:
            st.markdown(
                "<p style='color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;"
                "letter-spacing:0.1em;margin:8px 0 6px 0'>Strategy</p>",
                unsafe_allow_html=True,
            )
            strat_names = [s["name"] for s in scalp_strats]
            current = st.session_state.get("active_strategy", "luxalgo_smc")
            try:
                idx = strat_names.index(current)
            except ValueError:
                idx = 0
            selected = st.selectbox(
                "Strategy",
                strat_names,
                format_func=lambda n: next((s["label"] for s in scalp_strats if s["name"] == n), n),
                index=idx,
                key="strategy_select",
                label_visibility="collapsed",
            )
            if selected != current:
                st.session_state.active_strategy = selected
                st.rerun()
        elif scalp_strats:
            st.session_state.active_strategy = scalp_strats[0]["name"]

        st.divider()

        # ---- Auto-refresh controls -------------------------------------------
        st.markdown(
            "<p style='color:var(--text-muted);font-size:0.7rem;text-transform:uppercase;"
            "letter-spacing:0.1em;margin:0 0 6px 0'>Live Data</p>",
            unsafe_allow_html=True,
        )
        auto_refresh = st.toggle(
            "Auto-refresh prices",
            value=st.session_state.get("auto_refresh", True),
            key="auto_refresh_toggle",
        )
        st.session_state.auto_refresh = auto_refresh
        if auto_refresh:
            refresh_iv = st.slider(
                "Refresh interval (s)",
                5, 60,
                st.session_state.get("refresh_interval", 15),
                step=5,
                key="refresh_interval_slider",
            )
            st.session_state.refresh_interval = refresh_iv

        st.divider()

        # ---- Footer status --------------------------------------------------
        st.markdown(
            f"""
            <div style="font-size:0.75rem;color:var(--text-muted);line-height:1.6">
              <div>MT5: <b style="color:{'#2ecc71' if client.is_connected() else '#ef5350'}">
                {'● connected' if client.is_connected() else '● offline'}</b>
              </div>
              <div>Symbol: <b style="color:var(--text-primary)">{st.session_state.get("symbol")}</b></div>
              <div>Time: <b style="color:var(--text-primary)">{time.strftime("%H:%M:%S UTC", time.gmtime())}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return choice


# --- Setup --------------------------------------------------------------------
def _setup() -> None:
    st.set_page_config(
        page_title="AURIC — XAUUSD Trading Bot",
        page_icon="🟡",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_global_styles()
    st.markdown(
        '<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">',
        unsafe_allow_html=True,
    )
    cfg = get_config()
    st.session_state.setdefault("cfg", cfg)
    st.session_state.setdefault("symbol", cfg.get("app", {}).get("symbol", "XAUUSD-VIP"))
    st.session_state.setdefault("mode", get_trading_mode())
    st.session_state.setdefault("strategy_mode", "swing")
    st.session_state.setdefault("active_strategy", cfg.get("strategy", {}).get("active_strategy", "luxalgo_smc"))
    st.session_state.setdefault("auto_refresh", True)
    st.session_state.setdefault("refresh_interval", 15)

    # Global auto-refresh (all pages)
    if st.session_state.get("auto_refresh", True):
        interval = st.session_state.get("refresh_interval", 15) * 1000
        st_autorefresh(interval=interval, key="global_refresh")


# --- Main ---------------------------------------------------------------------
def main() -> None:
    _setup()
    _render_appbar()
    choice = _sidebar()

    if choice == "Overview":
        from dashboard.views import home
        home.render()
    elif choice == "Live Chart":
        from dashboard.views import live_chart
        live_chart.render()
    elif choice == "Signals":
        from dashboard.views import signals
        signals.render()
    elif choice == "Trades":
        from dashboard.views import trades
        trades.render()
    elif choice == "Performance":
        from dashboard.views import performance
        performance.render()
    elif choice == "Backtest":
        from dashboard.views import backtest
        backtest.render()
    elif choice == "Strategy Maker":
        from dashboard.views import strategy_maker
        strategy_maker.render()
    elif choice == "Settings":
        from dashboard.views import settings
        settings.render()
    elif choice == "Logs":
        from dashboard.views import logs
        logs.render()


if __name__ == "__main__":
    main()
