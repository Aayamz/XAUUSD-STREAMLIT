"""Modern dark theme for the XAUUSD SMC Bot dashboard.

Single source of truth for the visual design. Inject via ``inject_css()``
at the top of ``dashboard/app.py``.

Palette is inspired by modern fintech/trading platforms (TradingView, Binance,
Linear) — deep navy backdrop, gold primary, teal/coral for direction, soft
borders and generous spacing.
"""
from __future__ import annotations

import streamlit as st


_CSS = """
<style>
/* ============================================================ */
/*  1.  ROOT TOKENS                                              */
/* ============================================================ */
:root {
    --bg-base:        #0a0e1a;
    --bg-elev-1:      #11151f;
    --bg-elev-2:      #161b2c;
    --bg-elev-3:      #1c2236;
    --border:         #232a36;
    --border-soft:    #1a2030;

    --text-primary:   #e8eaed;
    --text-secondary: #a8b0bf;
    --text-muted:     #6b7385;
    --text-inverse:   #0a0e1a;

    --accent:         #f0b90b;   /* gold */
    --accent-dim:     #b88800;
    --buy:            #26a69a;   /* teal */
    --sell:           #ef5350;   /* coral red */
    --info:           #5b8def;
    --warn:           #f5a623;
    --ok:             #2ecc71;

    --radius-sm:      6px;
    --radius:         10px;
    --radius-lg:      16px;

    --shadow-sm:      0 1px 2px rgba(0,0,0,0.25);
    --shadow:         0 4px 12px rgba(0,0,0,0.35);
    --shadow-lg:      0 12px 32px rgba(0,0,0,0.45);
}

/* ============================================================ */
/*  2.  GLOBAL TYPOGRAPHY                                        */
/* ============================================================ */
html, body, .stApp, [class*="css"]  {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI",
                 Roboto, "Helvetica Neue", sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    letter-spacing: -0.01em;
}

.stApp {
    background:
        radial-gradient(1200px 600px at 0% 0%, rgba(99,102,241,0.05), transparent 60%),
        radial-gradient(900px 500px at 100% 0%, rgba(240,185,11,0.04), transparent 60%),
        var(--bg-base) !important;
    color: var(--text-primary);
}

h1, h2, h3, h4, h5 {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

code, pre, .stCode {
    font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace !important;
    font-size: 0.85em !important;
}

/* ============================================================ */
/*  3.  STREAMLIT CHROME                                         */
/* ============================================================ */
#MainMenu, footer, .viewerBadge_link__qRIco { display: none !important; }
header[data-testid="stHeader"] {
    background: var(--bg-base) !important;
    border-bottom: 1px solid var(--border-soft) !important;
}

section[data-testid="stSidebar"] {
    background: var(--bg-elev-1) !important;
    border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] .stMarkdown { color: var(--text-secondary); }
section[data-testid="stSidebar"] label { color: var(--text-secondary) !important; }

/* ============================================================ */
/*  4.  CARDS                                                    */
/* ============================================================ */
.xc-card {
    background: linear-gradient(180deg, var(--bg-elev-2) 0%, var(--bg-elev-1) 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    box-shadow: var(--shadow-sm);
    transition: border-color .2s, transform .2s, box-shadow .2s;
}
.xc-card:hover {
    border-color: var(--border);
    box-shadow: var(--shadow);
}
.xc-card-flat {
    background: var(--bg-elev-1);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 14px 16px;
}

.xc-stat {
    background: linear-gradient(180deg, var(--bg-elev-2) 0%, var(--bg-elev-1) 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 18px;
    box-shadow: var(--shadow-sm);
}
.xc-stat-label {
    color: var(--text-muted);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 500;
    margin: 0 0 6px 0;
}
.xc-stat-value {
    color: var(--text-primary);
    font-size: 1.45rem;
    font-weight: 600;
    line-height: 1.1;
    letter-spacing: -0.02em;
    margin: 0;
}
.xc-stat-sub {
    color: var(--text-muted);
    font-size: 0.72rem;
    margin: 4px 0 0 0;
}
.xc-stat-up   { color: var(--buy)  !important; }
.xc-stat-down { color: var(--sell) !important; }
.xc-stat-accent { color: var(--accent) !important; }

.xc-section-title {
    color: var(--text-muted);
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
    background: var(--accent);
    border-radius: 2px;
    display: inline-block;
}

/* ============================================================ */
/*  5.  BADGES / PILLS                                           */
/* ============================================================ */
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
.xc-badge-long   { background: rgba(38,166,154,0.12); color: var(--buy);  border-color: rgba(38,166,154,0.3); }
.xc-badge-short  { background: rgba(239,83,80,0.12);  color: var(--sell); border-color: rgba(239,83,80,0.3); }
.xc-badge-neutral{ background: rgba(168,176,191,0.1); color: var(--text-secondary); border-color: var(--border); }
.xc-badge-live   { background: rgba(46,204,113,0.12); color: var(--ok);  border-color: rgba(46,204,113,0.3); }
.xc-badge-mock   { background: rgba(245,166,35,0.12); color: var(--warn); border-color: rgba(245,166,35,0.3); }
.xc-badge-off    { background: rgba(239,83,80,0.12);  color: var(--sell); border-color: rgba(239,83,80,0.3); }
.xc-badge-on     { background: rgba(38,166,154,0.12); color: var(--buy);  border-color: rgba(38,166,154,0.3); }
.xc-badge-accent { background: rgba(240,185,11,0.12); color: var(--accent); border-color: rgba(240,185,11,0.3); }

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

/* ============================================================ */
/*  6.  METRICS / DATA                                           */
/* ============================================================ */
[data-testid="stMetric"] {
    background: var(--bg-elev-2);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 14px 16px;
    box-shadow: var(--shadow-sm);
}
[data-testid="stMetric"] label {
    color: var(--text-muted) !important;
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 500 !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: var(--text-primary) !important;
    font-size: 1.3rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em;
}
[data-testid="stMetricDelta"] svg { display: none; }

[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    overflow: hidden !important;
    background: var(--bg-elev-1) !important;
}

[data-testid="stExpander"] {
    background: var(--bg-elev-1) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}

/* ============================================================ */
/*  7.  BUTTONS                                                  */
/* ============================================================ */
.stButton > button,
button[kind] {
    border-radius: 8px !important;
    font-weight: 500 !important;
    letter-spacing: -0.01em;
    transition: all .15s ease !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow);
}
button[kind="primary"] {
    background: var(--accent) !important;
    color: var(--text-inverse) !important;
    border: none !important;
    font-weight: 600 !important;
}
button[kind="primary"]:hover {
    background: #ffce3a !important;
}
button[kind="secondary"] {
    background: var(--bg-elev-2) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
}

/* ============================================================ */
/*  8.  ALERTS                                                   */
/* ============================================================ */
.stAlert {
    border-radius: var(--radius) !important;
    border-left-width: 3px !important;
    background: var(--bg-elev-1) !important;
    border-color: var(--border) !important;
    color: var(--text-secondary) !important;
}

/* ============================================================ */
/*  9.  TABS                                                     */
/* ============================================================ */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: transparent;
    border-bottom: 1px solid var(--border);
    padding: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: var(--text-secondary) !important;
    border-radius: 8px 8px 0 0 !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
}
.stTabs [aria-selected="true"] {
    background: var(--bg-elev-2) !important;
    color: var(--accent) !important;
    border: 1px solid var(--border);
    border-bottom: 1px solid var(--bg-elev-2);
    margin-bottom: -1px;
}

/* ============================================================ */
/* 10.  TOGGLES / RADIO / SELECT                                 */
/* ============================================================ */
.stToggle label, .stRadio label {
    color: var(--text-secondary) !important;
}
.stSelectbox div[data-baseweb="select"] > div {
    background: var(--bg-elev-2) !important;
    border-color: var(--border) !important;
    color: var(--text-primary) !important;
    border-radius: 8px !important;
}

/* ============================================================ */
/* 11.  APP-BAR (custom top header)                              */
/* ============================================================ */
.xc-appbar {
    padding: 14px 24px;
    background: var(--bg-elev-1);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    border-radius: var(--radius);
    margin-bottom: 1rem;
}
.xc-appbar .brand {
    display: flex; align-items: center; gap: 10px;
    font-size: 1.05rem; font-weight: 600; color: var(--text-primary);
    letter-spacing: -0.02em;
}
.xc-appbar .brand .logo {
    width: 30px; height: 30px; border-radius: 8px;
    background: linear-gradient(135deg, #f0b90b 0%, #b88800 100%);
    display: flex; align-items: center; justify-content: center;
    color: #0a0e1a; font-weight: 800; font-size: 0.95rem;
    box-shadow: 0 2px 6px rgba(240,185,11,0.35);
}
.xc-appbar .meta {
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    color: var(--text-secondary); font-size: 0.85rem;
}
.xc-appbar .meta b { color: var(--text-primary); font-weight: 600; }

/* ============================================================ */
/* 12.  GRID (not used — Streamlit breaks CSS grid inside        */
/*      st.markdown. Use st.columns() instead.)                  */
/* ============================================================ */

/* ============================================================ */
/* 13.  P&L COLORS (helper)                                      */
/* ============================================================ */
.xc-pnl-pos { color: var(--buy)  !important; font-weight: 600; }
.xc-pnl-neg { color: var(--sell) !important; font-weight: 600; }
.xc-pnl-zero{ color: var(--text-muted) !important; }

/* ============================================================ */
/* 14.  SCROLLBAR                                                */
/* ============================================================ */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--bg-base); }
::-webkit-scrollbar-thumb {
    background: var(--border);
    border-radius: 5px;
    border: 2px solid var(--bg-base);
}
::-webkit-scrollbar-thumb:hover { background: var(--bg-elev-3); }

/* ============================================================ */
/* 15.  CONTAINER WIDTH                                          */
/* ============================================================ */
.block-container { padding-top: 4.5rem; padding-bottom: 3rem; max-width: 1400px; }

/* ============================================================ */
/* 16.  REASONING LIST                                           */
/* ============================================================ */
.xc-reasons-list { list-style: none; padding: 0; margin: 8px 0 0 0; }
.xc-reasons-list li {
    position: relative;
    padding: 7px 0 7px 20px;
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.45;
    border-bottom: 1px solid var(--border-soft);
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
    background: var(--accent);
    opacity: 0.7;
}
</style>
"""


def inject_css() -> None:
    """Call once at the top of the Streamlit app to apply the theme."""
    st.markdown(_CSS, unsafe_allow_html=True)
