"""Shared CSS injected once per page load."""

import streamlit as st


def inject_global_styles():
    st.markdown("""
    <style>
    /* ── Fonts & base ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* ── Hide default Streamlit chrome ── */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 4.5rem !important; padding-bottom: 3rem; max-width: 1400px; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #111418 !important;
        border-right: 1px solid #1e2329;
    }
    [data-testid="stSidebar"] > div:first-child { padding: 0.75rem 0; }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #2a2e35; border-radius: 2px; }

    /* ── Card base ── */
    .tb-card {
        background: #161b22;
        border: 0.5px solid #21262d;
        border-radius: 10px;
        padding: 12px 14px;
    }
    .tb-section-label {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #6e7681;
        margin-bottom: 6px;
    }
    .tb-label {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #8b949e;
        margin-bottom: 3px;
    }
    .tb-value {
        font-family: 'JetBrains Mono', monospace;
        font-size: 17px;
        font-weight: 500;
        color: #e6edf3;
    }
    .tb-value-sm {
        font-family: 'JetBrains Mono', monospace;
        font-size: 14px;
        font-weight: 500;
        color: #e6edf3;
    }
    .tb-value-danger  { color: #f85149; }
    .tb-value-success { color: #3fb950; }
    .tb-value-warning { color: #d29922; }
    .tb-value-muted   { color: #8b949e; }

    /* ── Pills ── */
    .tb-pill {
        display: inline-flex; align-items: center; gap: 4px;
        padding: 2px 8px; border-radius: 20px;
        font-size: 11px; font-weight: 500;
    }
    .tb-pill-short  { background: #3d1a1a; color: #f85149; }
    .tb-pill-long   { background: #122a1e; color: #3fb950; }
    .tb-pill-live   { background: #122a1e; color: #3fb950; }
    .tb-pill-swing  { background: #2d2208; color: #d29922; }
    .tb-pill-action { background: #122a1e; color: #3fb950; }
    .tb-pill-off    { background: #3d1a1a; color: #f85149; }

    /* ── Reason tags ── */
    .tb-tag {
        display: inline-flex;
        padding: 2px 8px; border-radius: 20px;
        font-size: 10px;
        border: 0.5px solid #30363d;
        color: #8b949e;
        white-space: nowrap;
    }

    /* ── Metric cards ── */
    .tb-metric {
        background: #0d1117;
        border-radius: 8px;
        padding: 8px 10px;
    }

    /* ── Market strip ── */
    .tb-market-strip {
        background: #161b22;
        border-bottom: 0.5px solid #21262d;
        display: flex;
        gap: 0;
    }
    .tb-market-cell {
        flex: 1;
        padding: 8px 14px;
        border-right: 0.5px solid #21262d;
    }
    .tb-market-cell:last-child { border-right: none; }

    /* ── Strategy card ── */
    .sm-card {
        background: #161b22;
        border: 0.5px solid #21262d;
        border-radius: 10px;
        padding: 12px;
    }
    .sm-card-featured { border: 1.5px solid #1f6feb; }
    .sm-code-tag {
        display: inline-flex;
        padding: 1px 6px; border-radius: 4px;
        font-size: 10px;
        font-family: 'JetBrains Mono', monospace;
        background: #0d1117; color: #8b949e;
    }
    .sm-btn {
        padding: 5px 12px;
        border: 0.5px solid #30363d;
        border-radius: 8px;
        font-size: 11px;
        cursor: pointer;
        background: transparent;
        color: #8b949e;
        font-family: 'Inter', sans-serif;
    }
    .sm-btn-active {
        background: #122a1e;
        border: none;
        color: #3fb950;
        font-weight: 500;
    }

    /* ── Header bar ── */
    .tb-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 8px 16px;
        background: #161b22;
        border-bottom: 0.5px solid #21262d;
        margin-bottom: 0;
    }

    /* ── CTA button ── */
    .tb-cta-btn {
        background: #2d2208;
        color: #d29922;
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        font-family: 'Inter', sans-serif;
        display: inline-flex; align-items: center; gap: 5px;
    }

    /* ── Signal history table ── */
    .tb-signal-table {
        width: 100%; border-collapse: collapse;
        font-size: 12px; font-family: 'JetBrains Mono', monospace;
    }
    .tb-signal-table th {
        font-size: 10px; text-transform: uppercase;
        letter-spacing: 0.06em; color: #6e7681;
        padding: 6px 10px; border-bottom: 0.5px solid #21262d;
        font-family: 'Inter', sans-serif; font-weight: 400;
        text-align: left;
    }
    .tb-signal-table td {
        padding: 8px 10px;
        border-bottom: 0.5px solid #161b22;
        color: #c9d1d9;
    }
    .tb-signal-table tr:nth-child(even) td { background: #0d1117; }

    /* ── Legacy xc- classes (used by app.py appbar, trades, live_chart, metrics) ── */
    .xc-card {
        background: linear-gradient(180deg, #161b2c 0%, #11151f 100%);
        border: 1px solid #232a36;
        border-radius: 10px;
        padding: 16px 18px;
    }
    .xc-card-flat {
        background: #11151f;
        border: 1px solid #1a2030;
        border-radius: 10px;
        padding: 14px 16px;
    }
    .xc-stat {
        background: linear-gradient(180deg, #161b2c 0%, #11151f 100%);
        border: 1px solid #232a36;
        border-radius: 10px;
        padding: 14px 18px;
    }
    .xc-stat-label {
        color: #6b7385;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 500;
        margin: 0 0 6px 0;
    }
    .xc-stat-value {
        color: #e8eaed;
        font-size: 1.45rem;
        font-weight: 600;
        line-height: 1.1;
        letter-spacing: -0.02em;
        margin: 0;
    }
    .xc-stat-sub {
        color: #6b7385;
        font-size: 0.72rem;
        margin: 4px 0 0 0;
    }
    .xc-stat-up   { color: #26a69a !important; }
    .xc-stat-down { color: #ef5350 !important; }
    .xc-stat-accent { color: #f0b90b !important; }
    .xc-section-title {
        color: #6b7385;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-weight: 600;
        margin: 18px 0 10px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .xc-section-title::before {
        content: "";
        width: 3px;
        height: 12px;
        background: #f0b90b;
        border-radius: 2px;
        display: inline-block;
    }
    .xc-badge {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 3px 9px;
        border-radius: 999px;
        font-size: 0.7rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        border: 1px solid transparent;
    }
    .xc-badge-long   { background: rgba(38,166,154,0.12); color: #26a69a; border-color: rgba(38,166,154,0.3); }
    .xc-badge-short  { background: rgba(239,83,80,0.12);  color: #ef5350; border-color: rgba(239,83,80,0.3); }
    .xc-badge-neutral{ background: rgba(168,176,191,0.1); color: #a8b0bf; border-color: #232a36; }
    .xc-badge-live   { background: rgba(46,204,113,0.12); color: #2ecc71; border-color: rgba(46,204,113,0.3); }
    .xc-badge-mock   { background: rgba(245,166,35,0.12); color: #f5a623; border-color: rgba(245,166,35,0.3); }
    .xc-badge-off    { background: rgba(239,83,80,0.12);  color: #ef5350; border-color: rgba(239,83,80,0.3); }
    .xc-badge-on     { background: rgba(38,166,154,0.12); color: #26a69a; border-color: rgba(38,166,154,0.3); }
    .xc-badge-accent { background: rgba(240,185,11,0.12); color: #f0b90b; border-color: rgba(240,185,11,0.3); }
    .xc-dot {
        display: inline-block;
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: currentColor;
        box-shadow: 0 0 0 0 currentColor;
        animation: xc-pulse 2s infinite;
    }
    @keyframes xc-pulse {
        0%   { box-shadow: 0 0 0 0   rgba(46,204,113,0.6); }
        70%  { box-shadow: 0 0 0 6px rgba(46,204,113,0);  }
        100% { box-shadow: 0 0 0 0   rgba(46,204,113,0);  }
    }
    .xc-pnl-pos { color: #26a69a !important; font-weight: 600; }
    .xc-pnl-neg { color: #ef5350 !important; font-weight: 600; }
    .xc-pnl-zero{ color: #6b7385 !important; }
    .xc-reasons-list { list-style: none; padding: 0; margin: 8px 0 0 0; }
    .xc-reasons-list li {
        position: relative;
        padding: 7px 0 7px 20px;
        font-size: 0.82rem;
        color: #a8b0bf;
        line-height: 1.45;
        border-bottom: 1px solid #1a2030;
    }
    .xc-reasons-list li:last-child { border-bottom: none; }
    .xc-reasons-list li::before {
        content: "";
        position: absolute;
        left: 0;
        top: 12px;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #f0b90b;
        opacity: 0.7;
    }
    </style>
    """, unsafe_allow_html=True)
