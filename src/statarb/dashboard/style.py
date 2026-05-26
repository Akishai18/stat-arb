"""Plotly styling — Bloomberg-terminal palette.

The CSS for surrounding Streamlit widgets is in `theme.py`. This module
exposes the color constants used by both, and a `base_layout()` helper
that returns the plotly layout dict for charts (black bg, amber title,
monospace, hairline gridlines, etc.)."""

from __future__ import annotations

import plotly.graph_objects as go

# --- Bloomberg-evocative palette ---
BG = "#000000"               # true black canvas
PANEL = "#0a0a0a"            # near-black panels
GRID = "#1a1a1a"             # hairline gridlines
BORDER = "#1f1f1f"
AMBER = "#ff8000"            # primary accent
AMBER_DIM = "#cc6600"
WHITE = "#e0e0e0"            # off-white body text
WHITE_DIM = "#8a8a8a"
GREEN = "#00d100"            # positive returns
RED = "#ff3030"              # negative returns
CYAN = "#22d3ee"             # secondary accent (rarely used)

# Backwards-compat aliases used by earlier views
PRIMARY = AMBER
SECONDARY = RED
ACCENT = CYAN
NEUTRAL = WHITE_DIM
GOOD = GREEN
BAD = RED


def base_layout(title: str = "") -> dict:
    """Plotly layout dict — black canvas, amber title, monospace, hairline grid."""
    return dict(
        title=dict(
            text=title.upper() if title else "",
            font=dict(family="IBM Plex Mono, monospace", color=AMBER, size=13),
            x=0.0,
            xanchor="left",
        ),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family="IBM Plex Mono, monospace", color=WHITE, size=11),
        margin=dict(l=50, r=20, t=40, b=40),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=PANEL,
            bordercolor=AMBER,
            font=dict(family="IBM Plex Mono, monospace", color=WHITE, size=11),
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom", y=1.02, xanchor="right", x=1,
            font=dict(family="IBM Plex Mono, monospace", color=WHITE, size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            gridcolor=GRID,
            zerolinecolor=GRID,
            tickfont=dict(family="IBM Plex Mono, monospace", color=WHITE_DIM, size=10),
            showline=True, linecolor=BORDER,
        ),
        yaxis=dict(
            gridcolor=GRID,
            zerolinecolor=GRID,
            tickfont=dict(family="IBM Plex Mono, monospace", color=WHITE_DIM, size=10),
            showline=True, linecolor=BORDER,
            tickfont_color=WHITE_DIM,
        ),
    )


def equity_curve_figure(
    strategy_eq,
    benchmark_eq=None,
    *,
    strategy_label: str = "STRATEGY (NET)",
    benchmark_label: str = "BENCHMARK",
    title: str = "EQUITY CURVE",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=strategy_eq.index, y=strategy_eq.values,
        mode="lines", name=strategy_label.upper(),
        line=dict(color=AMBER, width=1.6),
    ))
    if benchmark_eq is not None:
        bench = benchmark_eq.copy()
        first = bench.first_valid_index()
        if first is not None and bench.loc[first] != 0:
            bench = bench / bench.loc[first]
        fig.add_trace(go.Scatter(
            x=bench.index, y=bench.values,
            mode="lines", name=benchmark_label.upper(),
            line=dict(color=WHITE_DIM, width=1.0, dash="dot"),
        ))
    layout = base_layout(title)
    fig.update_layout(**layout)
    fig.update_yaxes(title=dict(text="GROWTH OF $1",
                                font=dict(family="IBM Plex Mono, monospace", color=AMBER_DIM, size=10)))
    return fig


def drawdown_figure(equity_curve, title: str = "DRAWDOWN") -> go.Figure:
    dd = equity_curve / equity_curve.cummax() - 1.0
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values,
        mode="lines", name="DRAWDOWN",
        line=dict(color=RED, width=1.0),
        fill="tozeroy", fillcolor="rgba(255, 48, 48, 0.25)",
    ))
    fig.update_layout(**base_layout(title))
    fig.update_yaxes(title=dict(text="DRAWDOWN",
                                font=dict(family="IBM Plex Mono, monospace", color=AMBER_DIM, size=10)),
                     tickformat=".0%")
    return fig


def metric_color(value: float, *, neutral: float = 0.0) -> str:
    if value > neutral:
        return GREEN
    if value < neutral:
        return RED
    return WHITE_DIM
