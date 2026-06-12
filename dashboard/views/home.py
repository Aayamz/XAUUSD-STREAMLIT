"""Overview / home page — at-a-glance status with modern card layout."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

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


def render() -> None:
    st_autorefresh(interval=10_000, key="home_refresh")
    symbol = st.session_state.get("symbol", "XAUUSD")
    cfg = st.session_state.get("cfg", {})
    ltf = cfg.get("strategy", {}).get("entry_timeframe", "M15")
    htf = cfg.get("strategy", {}).get("higher_timeframe", "H4")
    strategy_mode = st.session_state.get("strategy_mode", "swing")

    # ---- Market data ---------------------------------------------------------
    try:
        account = fetch_account()
        info = fetch_symbol_info(symbol)
        positions = fetch_positions(symbol)
    except Exception as e:  # noqa: BLE001
        st.error(f"MT5 not reachable: {e}")
        return

    # ---- Header bar ----------------------------------------------------------
    runner = get_bot_runner()
    auto = runner.is_running()
    strategy_mode_label = strategy_mode.upper()

    st.markdown(f"""
    <div class="tb-header">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-weight:500;color:#e6edf3">AURIC</span>
        <span class="tb-pill tb-pill-swing">{strategy_mode_label}</span>
      </div>
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:11px;color:#8b949e">{symbol}</span>
        <span class="tb-pill tb-pill-live">
          <span style="width:6px;height:6px;border-radius:50%;background:currentColor"></span>Live
        </span>
        <span class="tb-pill {'tb-pill-live' if auto else 'tb-pill-off'}">
          {'Auto-trading on' if auto else 'Auto-trading off'}
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Market strip (Bid / Ask / Spread / Contract) ------------------------
    if info:
        bid = float(info.get("bid", 0))
        ask = float(info.get("ask", 0))
        spread = float(info.get("spread", 0))
        contract = float(info.get("contract_size", 100))
    else:
        bid = ask = spread = 0
        contract = 100

    st.markdown(f"""
    <div class="tb-market-strip">
      <div class="tb-market-cell">
        <div class="tb-label">Bid</div>
        <div class="tb-value-sm">{bid:,.2f}</div>
      </div>
      <div class="tb-market-cell">
        <div class="tb-label">Ask</div>
        <div class="tb-value-sm">{ask:,.2f}</div>
      </div>
      <div class="tb-market-cell">
        <div class="tb-label">Spread</div>
        <div class="tb-value-sm tb-value-warning">{spread:,.2f}</div>
      </div>
      <div class="tb-market-cell">
        <div class="tb-label">Contract</div>
        <div class="tb-value-sm">{contract:.0f}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Account cards -------------------------------------------------------
    equity = float(account.get("equity", 0)) if account else 0
    balance = float(account.get("balance", 0)) if account else 0
    margin = float(account.get("margin", 0)) if account else 0
    free_margin = float(account.get("free_margin", 0)) if account else 0
    open_pnl = equity - balance

    st.markdown('<div class="tb-section-label" style="margin-top:14px">Account</div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="tb-card">
          <div class="tb-label">Balance</div>
          <div class="tb-value">${balance:,.2f}</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        pnl_color = "tb-value-success" if open_pnl >= 0 else "tb-value-danger"
        st.markdown(f"""
        <div class="tb-card">
          <div class="tb-label">Equity</div>
          <div class="tb-value">${equity:,.2f}</div>
          <div class="tb-value-sm {pnl_color}" style="font-size:11px;margin-top:2px">
            ${open_pnl:+,.2f} open P/L
          </div>
        </div>""", unsafe_allow_html=True)
    with col3:
        margin_pct = round((margin / equity * 100), 1) if equity else 0
        st.markdown(f"""
        <div class="tb-card">
          <div class="tb-label">Free margin</div>
          <div class="tb-value">${free_margin:,.2f}</div>
          <div style="font-size:11px;color:#8b949e;margin-top:2px">{margin_pct}% used</div>
        </div>""", unsafe_allow_html=True)

    # ---- Performance summary -------------------------------------------------
    daily_pnl, win_rate, pf, trades = 0.0, 0.0, 0.0, 0
    try:
        deals = fetch_history(days=30)
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

    open_positions = len(positions) if positions else 0

    st.markdown('<div class="tb-section-label" style="margin-top:12px">Performance</div>', unsafe_allow_html=True)
    pc1, pc2, pc3, pc4, pc5 = st.columns(5)
    perf_items = [
        ("Open", str(open_positions), ""),
        ("Daily P&L", f"+${daily_pnl:,.0f}" if daily_pnl >= 0 else f"-${abs(daily_pnl):,.0f}",
         "tb-value-success" if daily_pnl >= 0 else "tb-value-danger"),
        ("Win rate", f"{win_rate:.1f}%",
         "tb-value-success" if win_rate >= 50 else ("tb-value-warning" if win_rate >= 30 else "tb-value-danger")),
        ("Prof. factor", f"{pf:.2f}" if pf != float("inf") and pf < 90 else "\u221e", ""),
        ("Trades", str(trades), ""),
    ]
    for col, (label, value, color_class) in zip([pc1, pc2, pc3, pc4, pc5], perf_items):
        with col:
            st.markdown(f"""
            <div class="tb-metric">
              <div class="tb-label">{label}</div>
              <div class="tb-value-sm {color_class}" style="font-size:16px">{value}</div>
            </div>""", unsafe_allow_html=True)

    # ---- Latest signal with confidence ring gauge ----------------------------
    _render_signal_card(symbol, cfg, ltf, htf, strategy_mode)


def _render_signal_card(symbol: str, cfg: dict, ltf: str, htf: str,
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
    conf = float(sig.confidence)
    entry = sig.entry
    sl = sig.stop_loss
    tp = sig.take_profit
    rr = sig.rr
    reasons = sig.reasons

    # Save to control bus for manual trade
    bus = get_control_bus()
    confidence_threshold = 50.0 if strategy_mode == "scalp" else 55.0
    min_rr = 1.0 if strategy_mode == "scalp" else 2.0
    is_actionable = (
        direction != "NEUTRAL"
        and conf >= confidence_threshold
        and entry > 0
        and sl > 0
        and tp > 0
        and rr >= min_rr
    )
    bus.update_signal({
        "direction": direction,
        "confidence": conf,
        "entry": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "rr": rr,
        "reasons": reasons,
        "timestamp": sig.timestamp,
        "is_actionable": is_actionable,
        "strategy_mode": strategy_mode,
    })

    # SVG arc ring maths (r=36, circumference=226.19)
    circumference = 226.19
    offset = round(circumference * (1 - conf / 100), 2)

    dir_color = "#f85149" if direction == "SHORT" else "#3fb950"
    arc_color = "#d29922"  # amber gold — matches XAU theme

    risk_pts = round(abs(entry - sl), 2) if entry and sl else 0
    reward_pts = round(abs(tp - entry), 2) if tp and entry else 0

    reasons_html = "".join(f'<span class="tb-tag">{r}</span>' for r in reasons)

    strategy_label = next(
        (s.get("label", s["name"]) for s in
         __import__("strategy", fromlist=["list_strategies"]).list_strategies()
         if s["name"] == st.session_state.get("active_strategy")),
        strategy_mode,
    )

    st.markdown('<div class="tb-section-label" style="margin-top:12px">Latest signal</div>',
                unsafe_allow_html=True)
    st.markdown(f"""
    <div class="tb-card" style="margin-bottom:8px">
      <div style="display:flex;gap:16px;align-items:flex-start">

        <!-- Confidence ring gauge -->
        <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0">
          <svg width="96" height="96" viewBox="0 0 96 96">
            <circle cx="48" cy="48" r="36" fill="none"
              stroke="#21262d" stroke-width="7"/>
            <circle cx="48" cy="48" r="36" fill="none"
              stroke="{arc_color}" stroke-width="7"
              stroke-dasharray="{circumference}"
              stroke-dashoffset="{offset}"
              stroke-linecap="round"
              transform="rotate(-90 48 48)"/>
            <text x="48" y="44" text-anchor="middle"
              font-size="10" font-weight="500"
              style="fill:{dir_color};font-family:Inter,sans-serif">{direction}</text>
            <text x="48" y="62" text-anchor="middle"
              font-size="19" font-weight="500"
              style="fill:{arc_color};font-family:'JetBrains Mono',monospace">{conf:.0f}%</text>
          </svg>
          <div style="font-size:10px;color:#6e7681;text-transform:uppercase;
               letter-spacing:.07em;margin-top:-4px">Confidence</div>
        </div>

        <!-- Signal details -->
        <div style="flex:1;min-width:0">
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px">
            <div>
              <div class="tb-label">Entry</div>
              <div class="tb-value-sm">{entry:,.2f}</div>
            </div>
            <div>
              <div class="tb-label">Stop loss</div>
              <div class="tb-value-sm tb-value-danger">{sl:,.2f}</div>
            </div>
            <div>
              <div class="tb-label">Take profit</div>
              <div class="tb-value-sm tb-value-success">{tp:,.2f}</div>
            </div>
            <div>
              <div class="tb-label">R:R ratio</div>
              <div class="tb-value-sm">{rr:.2f}</div>
            </div>
          </div>

          <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px;align-items:center">
            <span style="font-size:10px;color:#6e7681;margin-right:2px">Reasons:</span>
            {reasons_html}
          </div>

          <div style="display:flex;align-items:center;gap:8px">
            {'<span class="tb-pill tb-pill-action"><span style="width:5px;height:5px;border-radius:50%;background:currentColor;display:inline-block"></span>Actionable</span>' if is_actionable else '<span style="font-size:11px;color:#6e7681">Not actionable</span>'}
            <span style="font-size:11px;color:#6e7681">{strategy_label}</span>
          </div>
        </div>
      </div>

      <!-- CTA row -->
      <div style="border-top:0.5px solid #21262d;margin-top:12px;padding-top:10px;
           display:flex;align-items:center;justify-content:space-between">
        <div style="display:flex;gap:16px">
          <span style="font-size:12px;color:#6e7681">Risk
            <span style="color:#f85149;font-family:'JetBrains Mono',monospace;font-weight:500">
              {risk_pts} pts</span></span>
          <span style="font-size:12px;color:#6e7681">Reward
            <span style="color:#3fb950;font-family:'JetBrains Mono',monospace;font-weight:500">
              {reward_pts} pts</span></span>
          <span style="font-size:12px;color:#6e7681">R:R
            <span style="color:#e6edf3;font-family:'JetBrains Mono',monospace;font-weight:500">
              {rr:.2f}</span></span>
        </div>
        <span style="font-size:11px;color:#6e7681">{strategy_mode.upper()}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Manual trade button
    if is_actionable:
        if st.button("Execute Trade Now", type="primary", width="stretch",
                     key="execute_signal"):
            bus.push({"type": "MANUAL_TRADE", "signal_data": bus.get_last_signal()})
            st.toast("Trade queued — runs on next bot tick.", icon="🚀")
