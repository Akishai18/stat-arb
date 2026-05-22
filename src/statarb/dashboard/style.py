"""Consistent plotly styling for dashboard charts."""

from __future__ import annotations

import plotly.graph_objects as go

PRIMARY = "#1f4e79"      # deep blue: strategy
SECONDARY = "#7b241c"    # deep red: drawdown / loss
ACCENT = "#2e75b6"       # mid blue: secondary series
NEUTRAL = "#a6a6a6"      # gray: benchmark / out-regime
GOOD = "#1f7a3a"         # green
BAD = "#c0392b"          # red


def base_layout(title: str = "") -> dict:
    return dict(
        title=title,
        template="simple_white",
        margin=dict(l=40, r=20, t=50, b=40),
        font=dict(size=12),
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11)),
    )


def equity_curve_figure(
    strategy_eq,
    benchmark_eq=None,
    *,
    strategy_label: str = "strategy (net)",
    benchmark_label: str = "benchmark",
    title: str = "Equity curve",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=strategy_eq.index, y=strategy_eq.values,
        mode="lines", name=strategy_label,
        line=dict(color=PRIMARY, width=2),
    ))
    if benchmark_eq is not None:
        # Normalize the benchmark to start at the strategy's first value.
        bench = benchmark_eq.copy()
        first = bench.first_valid_index()
        if first is not None and bench.loc[first] != 0:
            bench = bench / bench.loc[first]
        fig.add_trace(go.Scatter(
            x=bench.index, y=bench.values,
            mode="lines", name=benchmark_label,
            line=dict(color=NEUTRAL, width=1.5, dash="dash"),
        ))
    fig.update_layout(**base_layout(title))
    fig.update_yaxes(title_text="growth of $1")
    return fig


def drawdown_figure(equity_curve, title: str = "Drawdown") -> go.Figure:
    dd = equity_curve / equity_curve.cummax() - 1.0
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dd.index, y=dd.values,
        mode="lines", name="drawdown",
        line=dict(color=SECONDARY, width=1.5),
        fill="tozeroy", fillcolor="rgba(192, 57, 43, 0.35)",
    ))
    fig.update_layout(**base_layout(title))
    fig.update_yaxes(title_text="drawdown", tickformat=".0%")
    return fig


def metric_color(value: float, *, neutral: float = 0.0) -> str:
    if value > neutral:
        return GOOD
    if value < neutral:
        return BAD
    return NEUTRAL
