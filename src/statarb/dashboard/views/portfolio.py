"""Portfolio tab: weight time series, exposure, turnover, position utilization."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from statarb.dashboard.state import POSITION_CAP, DashboardState
from statarb.dashboard.style import ACCENT, BAD, NEUTRAL, PRIMARY, base_layout


def render(state: DashboardState) -> None:
    weights = state.opt_weights.dropna(how="all")
    headline = state.optimizer_by_cost[state.headline_cost]

    st.subheader("Portfolio diagnostics")
    st.caption(f"Optimizer weights from the locked Phase 7 strategy at {state.headline_cost} bps/side.")

    # Weight time series
    fig = go.Figure()
    palette = ["#1f4e79", "#2e75b6", "#9dc3e6", "#7b241c", "#c0392b"]
    for col, color in zip(weights.columns, palette, strict=False):
        fig.add_trace(go.Scatter(
            x=weights.index, y=weights[col].values,
            mode="lines", name=col,
            line=dict(color=color, width=1.2),
        ))
    fig.add_hline(y=POSITION_CAP, line_color=NEUTRAL, line_dash="dot", annotation_text=f"+{POSITION_CAP:.0%} cap")
    fig.add_hline(y=-POSITION_CAP, line_color=NEUTRAL, line_dash="dot", annotation_text=f"-{POSITION_CAP:.0%} cap")
    fig.add_hline(y=0, line_color="black", line_width=0.5)
    fig.update_layout(**base_layout("Optimizer weights over time"))
    fig.update_yaxes(title_text="weight")
    st.plotly_chart(fig, width='stretch')

    # Gross / net exposure
    gross = weights.abs().sum(axis=1)
    net = weights.sum(axis=1)
    exp_fig = go.Figure()
    exp_fig.add_trace(go.Scatter(
        x=gross.index, y=gross.values,
        mode="lines", name="gross exposure",
        line=dict(color=PRIMARY, width=1.5),
    ))
    exp_fig.add_trace(go.Scatter(
        x=net.index, y=net.values,
        mode="lines", name="net exposure",
        line=dict(color=ACCENT, width=1.2),
    ))
    exp_fig.add_hline(y=1.0, line_color=NEUTRAL, line_dash="dot", annotation_text="gross cap = 1.0")
    exp_fig.add_hline(y=0.05, line_color=NEUTRAL, line_dash="dot", annotation_text="+5% net cap")
    exp_fig.add_hline(y=-0.05, line_color=NEUTRAL, line_dash="dot")
    exp_fig.update_layout(**base_layout("Gross + net exposure"))
    exp_fig.update_yaxes(title_text="exposure")
    st.plotly_chart(exp_fig, width='stretch')

    # Turnover
    turn = headline.turnover.loc[weights.index]
    turn_fig = go.Figure()
    turn_fig.add_trace(go.Bar(
        x=turn.index, y=turn.values,
        name="daily turnover",
        marker=dict(color=BAD, opacity=0.55),
    ))
    turn_fig.update_layout(**base_layout("Daily turnover (sum |Δw|)"))
    turn_fig.update_yaxes(title_text="turnover")
    st.plotly_chart(turn_fig, width='stretch')

    # Position-cap utilization: max(|w_i|) per day
    max_abs = weights.abs().max(axis=1)
    util_fig = go.Figure()
    util_fig.add_trace(go.Scatter(
        x=max_abs.index, y=(max_abs / POSITION_CAP).values,
        mode="lines", name="utilization",
        line=dict(color=ACCENT, width=1.2),
    ))
    util_fig.add_hline(y=1.0, line_color=NEUTRAL, line_dash="dot", annotation_text="cap")
    util_fig.update_layout(**base_layout(f"Position-cap utilization (|w_i| / {POSITION_CAP:.0%})"))
    util_fig.update_yaxes(title_text="fraction of cap", range=[0, 1.05])
    st.plotly_chart(util_fig, width='stretch')
