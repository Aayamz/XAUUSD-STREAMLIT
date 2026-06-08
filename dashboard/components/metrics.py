"""Modern metric card row — uses HTML/CSS rather than st.metric for full control.

Renders a 6-up row of stat cards with up/down/accent color variants.
"""
from __future__ import annotations

import streamlit as st


def _stat(label: str, value: str, sub: str = "", tone: str = "neutral") -> str:
    cls = {
        "neutral": "",
        "up":      "xc-stat-up",
        "down":    "xc-stat-down",
        "accent":  "xc-stat-accent",
    }.get(tone, "")
    return f"""
    <div class="xc-stat">
      <p class="xc-stat-label">{label}</p>
      <p class="xc-stat-value {cls}">{value}</p>
      <p class="xc-stat-sub">{sub}</p>
    </div>
    """


def _fmt_money(v: float, decimals: int = 2, signed: bool = False) -> str:
    """Format a dollar value. Set signed=True to show + for positive values."""
    if signed:
        if v > 0:
            return f"+${abs(v):,.{decimals}f}"
        if v < 0:
            return f"\u2212${abs(v):,.{decimals}f}"
    return f"${v:,.{decimals}f}"


def render_market(symbol_info: dict | None) -> None:
    """Render the market-data row (bid / ask / spread / contract size)."""
    cols = st.columns(4)
    if symbol_info:
        bid = float(symbol_info.get("bid", 0))
        ask = float(symbol_info.get("ask", 0))
        spread = float(symbol_info.get("spread", 0))
        digits = int(symbol_info.get("digits", 2))
        contract = float(symbol_info.get("contract_size", 100))
        with cols[0]:
            st.markdown(_stat("Bid", f"{bid:,.{digits}f}"), unsafe_allow_html=True)
        with cols[1]:
            st.markdown(_stat("Ask", f"{ask:,.{digits}f}"), unsafe_allow_html=True)
        with cols[2]:
            st.markdown(_stat("Spread", f"{spread:.{digits}f}"), unsafe_allow_html=True)
        with cols[3]:
            st.markdown(_stat("Contract", f"{contract:.0f}"), unsafe_allow_html=True)
    else:
        for c in cols:
            c.info("No symbol info")


def render_account(account: dict | None) -> None:
    """Render the account row (balance / equity / margin / free margin)."""
    cols = st.columns(4)
    if not account:
        for c in cols:
            c.info("No account info")
        return
    equity = float(account.get("equity", 0))
    balance = float(account.get("balance", 0))
    margin = float(account.get("margin", 0))
    free = float(account.get("free_margin", 0))
    pnl_today = equity - balance
    tone = "up" if pnl_today > 0 else ("down" if pnl_today < 0 else "neutral")
    with cols[0]:
        st.markdown(_stat("Balance", _fmt_money(balance, signed=False)), unsafe_allow_html=True)
    with cols[1]:
        st.markdown(_stat("Equity", _fmt_money(equity, signed=False),
                          sub=_fmt_money(pnl_today, signed=True) + " open P/L", tone=tone),
                    unsafe_allow_html=True)
    with cols[2]:
        st.markdown(_stat("Margin", _fmt_money(margin, signed=False)), unsafe_allow_html=True)
    with cols[3]:
        st.markdown(_stat("Free Margin", _fmt_money(free, signed=False)), unsafe_allow_html=True)


def render_perf(perf: dict | None, positions: list[dict] | None = None) -> None:
    """Render the performance row (positions count / daily P&L / win rate / PF)."""
    perf = perf or {}
    positions = positions or []
    n_pos = len(positions)
    daily = float(perf.get("daily_pnl", 0))
    wr = float(perf.get("win_rate", 0))
    pf = float(perf.get("profit_factor", 0))
    trades = int(perf.get("trades", 0))

    pf_str = f"{pf:.2f}" if pf < 90 else "\u221e"
    cols = st.columns(5)
    cols[0].markdown(_stat("Open Positions", str(n_pos)), unsafe_allow_html=True)
    cols[1].markdown(
        _stat("Daily P&L", _fmt_money(daily, signed=True),
              tone="up" if daily > 0 else ("down" if daily < 0 else "neutral")),
        unsafe_allow_html=True,
    )
    cols[2].markdown(_stat("Win Rate", f"{wr:.1f}%"), unsafe_allow_html=True)
    cols[3].markdown(_stat("Profit Factor", pf_str), unsafe_allow_html=True)
    cols[4].markdown(_stat("Total Trades", str(trades)), unsafe_allow_html=True)
