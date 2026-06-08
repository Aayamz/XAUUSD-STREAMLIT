"""Reusable Plotly chart for XAUUSD with LuxAlgo annotations."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from strategy import create_strategy


def build_chart(
    df: pd.DataFrame,
    annotations: dict[str, Any] | None = None,
    title: str = "XAUUSD",
    show_emas: bool = True,
    height: int = 720,
) -> go.Figure:
    """Build the full annotated chart.

    ``annotations`` is the dict returned by ``LuxAlgoSMC.annotate(df)``.
    """
    fig = go.Figure()

    # --- candlesticks
    fig.add_trace(
        go.Candlestick(
            x=df["time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Price",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        )
    )

    # --- EMAs
    if show_emas:
        for col, color, name in [
            ("ema20", "#fb8c00", "EMA 20"),
            ("ema50", "#42a5f5", "EMA 50"),
            ("ema200", "#ab47bc", "EMA 200"),
        ]:
            if col in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df["time"],
                        y=df[col],
                        name=name,
                        line=dict(color=color, width=1.2),
                    )
                )

    # --- Order Blocks (rectangles)
    if annotations and "order_blocks" in annotations:
        for ob in annotations["order_blocks"]:
            color = "rgba(38, 166, 154, 0.18)" if ob.is_bullish else "rgba(239, 83, 80, 0.18)"
            line_color = "#26a69a" if ob.is_bullish else "#ef5350"
            fig.add_shape(
                type="rect",
                x0=df["time"].iloc[max(ob.index, 0)],
                x1=df["time"].iloc[-1],
                y0=ob.bottom,
                y1=ob.top,
                line=dict(color=line_color, width=1),
                fillcolor=color,
                layer="below",
            )

    # --- FVGs
    if annotations and "fvgs" in annotations:
        for fvg in annotations["fvgs"]:
            color = "rgba(38, 166, 154, 0.12)" if fvg.is_bullish else "rgba(239, 83, 80, 0.12)"
            fig.add_shape(
                type="rect",
                x0=df["time"].iloc[max(fvg.index, 0)],
                x1=df["time"].iloc[-1],
                y0=fvg.bottom,
                y1=fvg.top,
                line=dict(color="rgba(0,0,0,0)"),
                fillcolor=color,
                layer="below",
            )

    # --- Liquidity lines
    if annotations and "buy_liquidity" in annotations:
        for lvl in annotations["buy_liquidity"]:
            fig.add_hline(
                y=lvl.price,
                line=dict(color="#ffd54f", width=1, dash="dot"),
                annotation_text="BSL",
                annotation_position="right",
            )
    if annotations and "sell_liquidity" in annotations:
        for lvl in annotations["sell_liquidity"]:
            fig.add_hline(
                y=lvl.price,
                line=dict(color="#ffd54f", width=1, dash="dot"),
                annotation_text="SSL",
                annotation_position="right",
            )

    # --- Premium / Discount equilibrium
    if annotations and "premium_discount" in annotations:
        pd_zone = annotations["premium_discount"]
        if pd_zone and not pd.isna(pd_zone.get("eq", float("nan"))):
            fig.add_hline(
                y=pd_zone["eq"],
                line=dict(color="#90a4ae", width=1, dash="dash"),
                annotation_text=f"EQ ({pd_zone['zone']})",
                annotation_position="left",
            )

    # --- Swing markers
    if annotations and "df" in annotations:
        df_s = annotations["df"]
        sh = df_s.dropna(subset=["swing_h"]) if "swing_h" in df_s.columns else pd.DataFrame()
        sl = df_s.dropna(subset=["swing_l"]) if "swing_l" in df_s.columns else pd.DataFrame()
        if not sh.empty:
            fig.add_trace(go.Scatter(
                x=sh["time"], y=sh["swing_h"], mode="markers",
                marker=dict(symbol="triangle-down", size=9, color="#ef5350"),
                name="Swing High",
                showlegend=True,
            ))
        if not sl.empty:
            fig.add_trace(go.Scatter(
                x=sl["time"], y=sl["swing_l"], mode="markers",
                marker=dict(symbol="triangle-up", size=9, color="#26a69a"),
                name="Swing Low",
                showlegend=True,
            ))
        bos = df_s.dropna(subset=["bos"]) if "bos" in df_s.columns else pd.DataFrame()
        choch = df_s.dropna(subset=["choch"]) if "choch" in df_s.columns else pd.DataFrame()
        if not bos.empty:
            fig.add_trace(go.Scatter(
                x=bos["time"], y=bos["close"], mode="markers",
                marker=dict(symbol="diamond", size=11, color="#42a5f5",
                            line=dict(color="white", width=1)),
                name="BOS", showlegend=True,
            ))
        if not choch.empty:
            fig.add_trace(go.Scatter(
                x=choch["time"], y=choch["close"], mode="markers",
                marker=dict(symbol="star", size=13, color="#ffd54f",
                            line=dict(color="white", width=1)),
                name="CHoCH", showlegend=True,
            ))

    fig.update_layout(
        title=title,
        height=height,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def build_equity_curve(equity: pd.Series) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity.index, y=equity.values, fill="tozeroy",
                             line=dict(color="#42a5f5"), name="Equity"))
    fig.update_layout(
        template="plotly_dark", height=320,
        margin=dict(l=10, r=10, t=20, b=10),
        yaxis_title="Equity (USD)",
    )
    return fig


def quick_annotate(df: pd.DataFrame, strategy=None, mode: str = "swing") -> dict[str, Any]:
    """Helper so the chart page stays tidy."""
    if strategy is not None:
        return strategy.annotate(df)
    return create_strategy("luxalgo_smc", mode=mode).annotate(df)