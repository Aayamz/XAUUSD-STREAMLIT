"""Signal detail panel — shows the latest signal with reasoning + lot suggestion."""
from __future__ import annotations

from typing import Any

import streamlit as st

from risk_manager.position_sizer import compute_lot_size
from strategy.luxalgo_smc import Direction, Signal


def _dir_color(d: Direction) -> str:
    return {"LONG": "#26a69a", "SHORT": "#ef5350"}.get(d.value, "#90a4ae")


def render(signal: Signal | None, equity: float | None, symbol_info: dict[str, Any] | None) -> None:
    if signal is None:
        st.info("No signal yet — waiting for next strategy cycle.")
        return

    # Get strategy mode from session state if available (for accurate actionability check)
    try:
        import streamlit as st
        strategy_mode = getattr(st.session_state, 'strategy_mode', 'swing') if hasattr(st, 'session_state') else 'swing'
    except:
        strategy_mode = 'swing'
    
    confidence_threshold = 50.0 if strategy_mode == "scalp" else 55.0
    min_rr = 1.0 if strategy_mode == "scalp" else 2.0
    
    # Check actionability with mode-specific thresholds
    is_actionable = (
        signal.direction != Direction.NEUTRAL
        and signal.confidence >= confidence_threshold
        and signal.entry > 0
        and signal.stop_loss > 0
        and signal.take_profit > 0
        and signal.rr >= min_rr
    )

    # ── Direction badge ───────────────────────────────────────────────────
    if signal.direction == Direction.NEUTRAL:
        st.markdown(
            '<span class="signal-badge flat">NEUTRAL</span>'
            f'  <span style="color:#9ca3af;margin-left:8px">confidence {signal.confidence:.0f}%</span>',
            unsafe_allow_html=True,
        )
    elif signal.direction == Direction.LONG:
        st.markdown(
            '<span class="signal-badge long">LONG</span>'
            f'  <span style="color:#9ca3af;margin-left:8px">confidence {signal.confidence:.0f}%</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="signal-badge short">SHORT</span>'
            f'  <span style="color:#9ca3af;margin-left:8px">confidence {signal.confidence:.0f}%</span>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Key levels ───────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Entry", f"{signal.entry:.2f}")
    col2.metric("Stop Loss", f"{signal.stop_loss:.2f}")
    col3.metric("Take Profit", f"{signal.take_profit:.2f}")
    col4.metric("R:R", f"{signal.rr:.2f}")

    # ── Actionability Status ───────────────────────────────────────────
    if is_actionable:
        st.success("✅ **TRADEABLE** - Signal meets all criteria")
    else:
        st.error("❌ **NOT TRADEABLE**")
        # Show why it's not actionable
        reasons_not_actionable = []
        if signal.direction == Direction.NEUTRAL:
            reasons_not_actionable.append("Direction is NEUTRAL")
        if signal.confidence < confidence_threshold:
            reasons_not_actionable.append(f"Confidence {signal.confidence:.1f}% < {confidence_threshold}% threshold")
        if signal.entry <= 0:
            reasons_not_actionable.append("Invalid entry price")
        if signal.stop_loss <= 0:
            reasons_not_actionable.append("Invalid stop loss")
        if signal.take_profit <= 0:
            reasons_not_actionable.append("Invalid take profit")
        if signal.rr < min_rr:
            reasons_not_actionable.append(f"RR {signal.rr:.2f} < {min_rr} minimum")
        
        for reason in reasons_not_actionable:
            st.markdown(f"• {reason}")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Reasoning ───────────────────────────────────────────────────
    with st.expander("Reasoning", expanded=True):
        for r in signal.reasons:
            st.markdown(f"- {r}")

    # ── Lot size suggestion ───────────────────────────────────────────────
    if is_actionable and equity and symbol_info:
        lots = compute_lot_size(equity, signal.entry, signal.stop_loss, symbol_info)
        risk_usd = lots * abs(signal.entry - signal.stop_loss) * 100
        st.success(
            f"Suggested lot size: **{lots:.2f}** (risk {risk_usd:.2f} USD)"
        )
    elif equity and symbol_info:
        st.info("Lot size calculation unavailable - signal not actionable")
    elif signal.direction == Direction.LONG:
        st.markdown(
            '<span class="signal-badge long">LONG</span>'
            f'  <span style="color:#9ca3af;margin-left:8px">confidence {signal.confidence:.0f}%</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="signal-badge short">SHORT</span>'
            f'  <span style="color:#9ca3af;margin-left:8px">confidence {signal.confidence:.0f}%</span>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Key levels ────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Entry", f"{signal.entry:.2f}")
    col2.metric("Stop Loss", f"{signal.stop_loss:.2f}")
    col3.metric("Take Profit", f"{signal.take_profit:.2f}")
    col4.metric("R:R", f"{signal.rr:.2f}")

    # ── Reasoning ─────────────────────────────────────────────────────────
    with st.expander("Reasoning", expanded=True):
        for r in signal.reasons:
            st.markdown(f"- {r}")

    # ── Lot size suggestion ───────────────────────────────────────────────
    # Check if signal is actionable based on current mode (we need to get mode from somewhere)
    # Since we don't have direct access to session state here, we'll use the signal's timestamp
    # to determine if it's recent enough, or we could pass mode as a parameter
    # For now, let's use a default check and improve this later if needed
    if signal.is_actionable() and equity and symbol_info:
        lots = compute_lot_size(equity, signal.entry, signal.stop_loss, symbol_info)
        risk_usd = lots * abs(signal.entry - signal.stop_loss) * 100
        st.success(
            f"Suggested lot size: **{lots:.2f}** (risk {risk_usd:.2f} USD)"
        )
