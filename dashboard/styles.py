import streamlit as st

GLOBAL_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">

<style>
/* ══ BASE ══ */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ══ KILL ALL DEFAULT STREAMLIT CHROME ══ */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
/* Hide default sidebar — navigation lives in fixed rail rendered in main content */
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="stSidebarNav"] + div,
footer { display: none !important; }

/* ══ MAIN CONTENT AREA ══ */
.block-container {
    margin-left: 200px !important;
    padding: 0.5rem 1.5rem 2.5rem !important;
    max-width: calc(100% - 200px) !important;
}

/* Strategy selector — constrain width */
[data-testid="stSelectbox"] { max-width: 280px !important; }

/* ══ SCROLLBAR ══ */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #2a2e35; border-radius: 2px; }

/* ══ SECTION LABEL ══ */
.tb-section-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #6e7681;
    margin: 18px 0 8px;
    padding: 0;
    line-height: 1;
}

/* ══ PAGE HEADER ══ */
.tb-page-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 0 0;
    margin-bottom: 0;
}

/* ══ MARKET STRIP ══ */
.tb-market-strip {
    display: flex;
    background: #161b22;
    border: 0.5px solid #21262d;
    border-radius: 10px;
    margin: 12px 0 0;
    overflow: hidden;
}
.tb-market-cell {
    flex: 1;
    padding: 10px 16px;
    border-right: 0.5px solid #21262d;
}
.tb-market-cell:last-child { border-right: none; }

/* ══ CARDS ══ */
.tb-card {
    background: #161b22;
    border: 0.5px solid #21262d;
    border-radius: 10px;
    padding: 14px 16px;
    height: 100%;
    box-sizing: border-box;
}
.tb-card-flat {
    background: #0d1117;
    border-radius: 8px;
    padding: 10px 12px;
    height: 100%;
    box-sizing: border-box;
}

/* ══ LABELS & VALUES ══ */
.tb-label {
    font-size: 10px; text-transform: uppercase;
    letter-spacing: 0.07em; color: #8b949e;
    margin-bottom: 4px; line-height: 1;
}
.tb-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px; font-weight: 500;
    color: #e6edf3; line-height: 1.2;
}
.tb-value-sm {
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px; font-weight: 500;
    color: #e6edf3; line-height: 1.2;
}
.tb-value-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: #6e7681;
    margin-top: 4px; line-height: 1;
}

/* ══ SEMANTIC COLORS ══ */
.c-danger  { color: #f85149 !important; }
.c-success { color: #3fb950 !important; }
.c-warning { color: #d29922 !important; }
.c-muted   { color: #8b949e !important; }
.c-info    { color: #79c0ff !important; }

/* ══ PILLS ══ */
.tb-pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 9px; border-radius: 20px;
    font-size: 11px; font-weight: 500; line-height: 1;
    white-space: nowrap;
}
.tb-pill-short   { background: #3d1a1a; color: #f85149; }
.tb-pill-long    { background: #122a1e; color: #3fb950; }
.tb-pill-live    { background: #122a1e; color: #3fb950; }
.tb-pill-swing   { background: #2d2208; color: #d29922; }
.tb-pill-scalp   { background: #1a1a3d; color: #79c0ff; }
.tb-pill-action  { background: #122a1e; color: #3fb950; }
.tb-pill-off     { background: #3d1a1a; color: #f85149; }
.tb-pill-neutral { background: #21262d; color: #8b949e; }

/* ══ REASON TAGS ══ */
.tb-tag {
    display: inline-flex; padding: 3px 9px; border-radius: 20px;
    font-size: 10px; line-height: 1;
    border: 0.5px solid #30363d; color: #8b949e; white-space: nowrap;
}

/* ══ DIVIDER ══ */
.tb-divider {
    border: none; border-top: 0.5px solid #21262d;
    margin: 14px 0;
}

/* ══ SIGNAL / DATA TABLE ══ */
.tb-table {
    width: 100%; border-collapse: collapse; font-size: 12px;
}
.tb-table th {
    font-size: 10px; font-family: 'Inter', sans-serif; font-weight: 400;
    text-transform: uppercase; letter-spacing: 0.07em; color: #6e7681;
    padding: 8px 12px; border-bottom: 0.5px solid #21262d; text-align: left;
}
.tb-table td {
    font-family: 'JetBrains Mono', monospace;
    padding: 10px 12px; border-bottom: 0.5px solid #161b22;
    color: #c9d1d9; white-space: nowrap;
}
.tb-table tbody tr:hover td { background: #161b22; }
.tb-table tbody tr:nth-child(even) td { background: #0a0d12; }

/* ══ STRATEGY CARDS ══ */
.sm-card {
    background: #161b22; border: 0.5px solid #21262d;
    border-radius: 10px; padding: 14px; height: 100%;
    box-sizing: border-box; display: flex; flex-direction: column; gap: 8px;
}
.sm-card-featured { border: 1.5px solid #1f6feb; }
.sm-code-tag {
    display: inline-flex; padding: 1px 6px; border-radius: 4px;
    font-size: 10px; font-family: 'JetBrains Mono', monospace;
    background: #0d1117; color: #8b949e;
}

/* ══ CTA BUTTON ══ */
.tb-cta-btn {
    display: inline-flex; align-items: center; gap: 6px;
    background: #2d2208; color: #d29922; border: none;
    border-radius: 8px; padding: 8px 20px;
    font-size: 13px; font-weight: 500; cursor: pointer;
    font-family: 'Inter', sans-serif;
}
.tb-cta-btn:hover { background: #3d2f0a; }

/* ══ PAGINATION ══ */
.tb-pager-info {
    font-size: 11px; color: #6e7681; padding-top: 6px;
}

/* ══ STREAMLIT COLUMN GAPS ══ */
[data-testid="stHorizontalBlock"] { gap: 8px !important; align-items: stretch !important; }
[data-testid="column"] { padding: 0 4px !important; }
</style>
"""


def inject_global_styles():
    """Call as the FIRST line in every render() function."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
