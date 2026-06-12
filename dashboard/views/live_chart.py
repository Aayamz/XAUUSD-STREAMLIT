"""Live chart page — the showpiece."""
from __future__ import annotations

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from dashboard.components.chart import build_chart, quick_annotate
from dashboard.state import (
    fetch_account, fetch_bars, fetch_positions, fetch_symbol_info, get_client, get_strategy,
)


# Map our internal timeframe labels to TradingView interval codes.
_TV_INTERVALS = {
    "M1": "1", "M3": "3", "M5": "5", "M15": "15", "M30": "30",
    "H1": "60", "H2": "120", "H4": "240", "D1": "D", "W1": "W", "MN1": "M",
}

# TradingView symbol suggestions for XAUUSD across common data vendors.
_TV_SYMBOLS = {
    "OANDA:XAUUSD": "OANDA (forex CFD)",
    "TVC:GOLD":      "TVC (spot gold)",
    "FX_IDC:XAUUSD": "IDC (spot)",
    "CAPITALCOM:GOLD": "Capital.com (gold)",
}


def render_tradingview(symbol: str, interval: str, height: int = 620) -> None:
    """Embed the free TradingView Advanced Chart widget.

    Uses the public ``tv.js`` widget — no API key required. Falls back to
    ``TVC:GOLD`` if our broker symbol isn't directly quoted on TradingView.
    """
    tv_symbol = st.session_state.get("tv_symbol", "OANDA:XAUUSD")
    interval_code = _TV_INTERVALS.get(interval, "15")

    symbol_options = list(_TV_SYMBOLS.keys())
    tv_symbol = st.selectbox(
        "TradingView data feed",
        symbol_options,
        index=symbol_options.index(tv_symbol) if tv_symbol in symbol_options else 0,
        format_func=lambda s: f"{s}  —  {_TV_SYMBOLS.get(s, '')}",
        key="tv_symbol_select",
    )
    st.session_state["tv_symbol"] = tv_symbol

    uid = "tv_xauusd_widget"
    html = f"""
    <div class="tradingview-widget-container" style="width:100%;height:{height}px;">
      <div id="{uid}" style="width:100%;height:100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
        new TradingView.widget({{
          "autosize": true,
          "symbol": "{tv_symbol}",
          "interval": "{interval_code}",
          "timezone": "Etc/UTC",
          "theme": "dark",
          "style": "1",
          "locale": "en",
          "toolbar_bg": "#0e1117",
          "backgroundColor": "#0e1117",
          "gridColor": "#1f2937",
          "enable_publishing": false,
          "withdateranges": true,
          "hide_side_toolbar": false,
          "allow_symbol_change": true,
          "details": false,
          "hotlist": false,
          "calendar": false,
          "studies": ["MASimple@tv-basicstudies"],
          "container_id": "{uid}"
        }});
      </script>
    </div>
    """
    st.components.v1.html(html, height=height + 10, scrolling=False)


def render() -> None:
    from dashboard.styles import inject_global_styles
    inject_global_styles()

    cfg = st.session_state.get("cfg", {})
    chart_cfg = cfg.get("dashboard", {})

    symbol = st.session_state.get("symbol", "XAUUSD")

    client = get_client()
    is_mock = client.name == "mock" if hasattr(client, "name") else False
    if is_mock:
        st.warning(
            "**MT5 feed is simulated** — positions opened from this session will be "
            "synthetic. The TradingView chart below is **live market data** and will "
            "show real XAUUSD prices regardless of MT5 connectivity."
        )

    tf = st.selectbox(
        "Timeframe",
        chart_cfg.get("available_timeframes", ["M5", "M15", "M30", "H1", "H4", "D1"]),
        index=chart_cfg.get("available_timeframes", ["M5", "M15", "M30", "H1", "H4", "D1"]).index(
            chart_cfg.get("default_timeframe", "H1")
        ) if chart_cfg.get("default_timeframe", "H1") in chart_cfg.get("available_timeframes", []) else 3,
        label_visibility="collapsed",
    )
    fc1, fc2, fc3 = st.columns([1, 1, 2])
    lookback = fc1.slider("Lookback (annotated)", 50, 800,
                          chart_cfg.get("chart_lookback_bars", 200), step=50,
                          label_visibility="collapsed")
    auto = fc2.toggle("Auto-refresh", value=True, label_visibility="collapsed")
    if auto:
        st_autorefresh(interval=15_000, key="chart_refresh")
    fc3.caption(f"{symbol} · {tf} · TradingView live feed")

    st.markdown('<p class="xc-section-title">Live Market Chart (TradingView)</p>',
                unsafe_allow_html=True)
    render_tradingview(symbol, tf)

    st.markdown('<p class="xc-section-title">Annotated Chart (Strategy Levels)</p>',
                unsafe_allow_html=True)
    try:
        df = fetch_bars(symbol, tf, lookback)
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to load bars: {e}")
        df = None

    if df is None or df.empty:
        st.warning("No data returned for annotated chart.")
        return

    strategy = get_strategy(
        st.session_state.get("strategy_mode", "swing"),
        strategy_name=st.session_state.get("active_strategy"),
    )
    annotations = quick_annotate(df, strategy, st.session_state.get("mode", "swing"))
    fig = build_chart(df, annotations=annotations, title=f"{symbol} · {tf}")
    st.plotly_chart(fig, width="stretch")

    with st.expander("Strategy Legend — what do the chart annotations mean?", expanded=False):
        st.markdown("""
        | Label | Full Name | Description |
        |-------|-----------|-------------|
        | **EMA 20 / 50 / 200** | Exponential Moving Average | Trend direction. Price above = bullish, below = bearish. Crossovers signal momentum shifts. |
        | **BOS** | Break of Structure | Price breaks a recent swing high/low — confirms trend continuation. Blue diamond. |
        | **CHoCH** | Change of Character | Price breaks structure in the *opposite* direction — signals a potential reversal. Gold star. |
        | **BSL** | Buy-Side Liquidity | Resting stop-loss orders above swing highs. Market makers often push price to "sweep" these. Dotted gold line. |
        | **SSL** | Sell-Side Liquidity | Resting stop-loss orders below swing lows. Same concept, opposite side. Dotted gold line. |
        | **EQ** | Equilibrium | Midpoint of the premium/discount zone. Price here is "fair value." Dashed grey line. |
        | **OB** | Order Block | Institutional supply/demand zone. Bullish OB = teal rectangle, bearish OB = red rectangle. Entry zones. |
        | **FVG** | Fair Value Gap | 3-bar price imbalance — price tends to return to fill these gaps. Faint teal/red rectangles. |
        | **Swing High** | Swing High | Local peak — forms the top of a structure range. Red triangle-down. |
        | **Swing Low** | Swing Low | Local trough — forms the bottom of a structure range. Teal triangle-up. |
        """, unsafe_allow_html=False)
        st.caption("**Strategy mode**: Swing uses H4/M15 timeframes with higher R:R targets. Scalp uses M15/M5 with tighter targets and faster entries.")
