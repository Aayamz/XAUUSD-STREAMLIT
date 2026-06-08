"""Settings page — MT5 creds, risk params, strategy toggles, sessions."""
from __future__ import annotations

import streamlit as st
import yaml

from utils.config import CONFIG_PATH, get_config, reload_config
from utils.encryption import load_credentials, mask, save_credentials


def render() -> None:
    st.markdown(
        "<h2 style='margin-bottom:4px'>Settings</h2>",
        unsafe_allow_html=True,
    )

    # ── MT5 Credentials ───────────────────────────────────────────────────
    st.markdown("#### MT5 Connection")
    st.caption("Enter your MetaTrader 5 demo account credentials below. "
               "The dashboard will switch from the mock feed to live market data "
               "the moment a valid connection is established.")

    creds = load_credentials()
    with st.form("creds_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        login = c1.text_input("Login (account number)", value=str(creds.get("login", "")))
        password = c1.text_input("Password", value=creds.get("password", ""), type="password")
        server = c2.text_input("Server", value=creds.get("server", ""),
                               placeholder="e.g. MetaQuotes-Demo")
        path = c2.text_input("Terminal path (optional)",
                             value=creds.get("path", ""),
                             placeholder="e.g. C:\\Program Files\\MetaTrader 5\\terminal64.exe")

        submitted = st.form_submit_button("Save & Connect", type="primary", width="stretch")
        if submitted:
            save_credentials({
                "login": login.strip(),
                "password": password,
                "server": server.strip(),
                "path": path.strip(),
            })
            st.success("Credentials saved (encrypted). Restart the dashboard to connect to live MT5.")

    if creds:
        st.caption(f"Currently stored: login={mask(str(creds.get('login', '')))}, "
                   f"server={mask(creds.get('server', ''), 3)}")

    st.divider()

    # ── Risk Parameters ───────────────────────────────────────────────────
    st.markdown("#### Risk Parameters")
    cfg = get_config()
    risk = cfg.get("risk", {})
    with st.form("risk_form"):
        c1, c2, c3 = st.columns(3)
        account_risk = c1.number_input("Risk per trade (%)",
                                        min_value=0.1, max_value=5.0,
                                        value=float(risk.get("account_risk_pct", 1.0)),
                                        step=0.1)
        daily_loss = c2.number_input("Daily loss limit (%)",
                                      min_value=1.0, max_value=10.0,
                                      value=float(risk.get("daily_loss_limit_pct", 4.0)),
                                      step=0.5)
        max_dd = c3.number_input("Max drawdown (%)",
                                 min_value=3.0, max_value=20.0,
                                 value=float(risk.get("max_drawdown_pct", 12.0)),
                                 step=0.5)

        c4, c5, c6 = st.columns(3)
        max_pos = c4.number_input("Max concurrent positions",
                                   min_value=1, max_value=5,
                                   value=int(risk.get("max_concurrent_positions", 1)))
        min_rr = c5.number_input("Minimum R:R",
                                  min_value=1.0, max_value=5.0,
                                  value=float(cfg.get("strategy", {}).get("min_rr", 2.0)),
                                  step=0.5)
        trailing = c6.checkbox("Trailing stop",
                               value=bool(risk.get("use_trailing_stop", True)))

        if st.form_submit_button("Save Risk Settings"):
            cfg.setdefault("risk", {}).update({
                "account_risk_pct": account_risk,
                "daily_loss_limit_pct": daily_loss,
                "max_drawdown_pct": max_dd,
                "max_concurrent_positions": max_pos,
                "use_trailing_stop": trailing,
            })
            cfg.setdefault("strategy", {})["min_rr"] = min_rr
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(cfg, f, sort_keys=False)
            reload_config()
            st.success("Risk settings saved.")

    st.divider()

    # ── Full config.yaml editor ───────────────────────────────────────────
    st.markdown("#### Advanced — config.yaml")
    with st.expander("Edit raw config"):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = f.read()
        edited = st.text_area("config.yaml", value=raw, height=280, label_visibility="collapsed")
        if st.button("Save config.yaml"):
            try:
                parsed = yaml.safe_load(edited)
                assert isinstance(parsed, dict)
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    yaml.safe_dump(parsed, f, sort_keys=False)
                reload_config()
                st.success("Saved. Restart the bot for some changes to apply.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Invalid YAML: {e}")
