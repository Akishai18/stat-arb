"""Costs tab: interactive cost slider + cost-sensitivity master table + chart."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from statarb.dashboard.state import COST_LEVELS_BPS, DashboardState, evaluate_cached
from statarb.dashboard.style import ACCENT, NEUTRAL, PRIMARY, base_layout


def render(state: DashboardState) -> None:
    st.subheader("Cost sensitivity")
    st.caption("Compare the Phase 7 optimizer to the equal-weight baseline across transaction-cost levels.")

    # Build the master cost table
    rows = []
    for bps in COST_LEVELS_BPS:
        opt = evaluate_cached(state.optimizer_by_cost[bps], state.spy_returns)
        base = evaluate_cached(state.baseline_by_cost[bps], state.spy_returns)
        rows.append({
            "Cost (bps/side)": bps,
            "Optimizer Sharpe": round(opt.sharpe, 3),
            "Optimizer CAGR": f"{opt.cagr:+.2%}",
            "Optimizer Max DD": f"{opt.max_drawdown:.2%}",
            "Baseline Sharpe": round(base.sharpe, 3),
            "Baseline CAGR": f"{base.cagr:+.2%}",
            "Baseline Max DD": f"{base.max_drawdown:.2%}",
        })
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    # Sharpe vs cost line chart
    bps_arr = list(COST_LEVELS_BPS)
    opt_sharpe = [evaluate_cached(state.optimizer_by_cost[b], state.spy_returns).sharpe for b in bps_arr]
    base_sharpe = [evaluate_cached(state.baseline_by_cost[b], state.spy_returns).sharpe for b in bps_arr]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=bps_arr, y=opt_sharpe,
        mode="lines+markers", name="optimizer (locked)",
        line=dict(color=PRIMARY, width=2.2),
        marker=dict(size=10),
    ))
    fig.add_trace(go.Scatter(
        x=bps_arr, y=base_sharpe,
        mode="lines+markers", name="baseline: eq-weight carry+cot",
        line=dict(color=NEUTRAL, width=1.6, dash="dash"),
        marker=dict(size=8),
    ))
    fig.add_hline(y=0, line_color="black", line_width=0.5)
    fig.update_layout(**base_layout("Sharpe vs transaction cost"))
    fig.update_xaxes(title_text="cost (bps per side)")
    fig.update_yaxes(title_text="Sharpe (full window)")
    st.plotly_chart(fig, width='stretch')

    st.divider()

    # Equity curves overlaid at all cost levels (optimizer)
    st.markdown("##### Optimizer equity curves across cost levels")
    palette = [PRIMARY, ACCENT, "#9dc3e6", "#c0392b"]
    eq_fig = go.Figure()
    for bps, color in zip(bps_arr, palette, strict=False):
        eq = state.optimizer_by_cost[bps].equity_curve
        eq_fig.add_trace(go.Scatter(
            x=eq.index, y=eq.values,
            mode="lines", name=f"{bps} bps",
            line=dict(color=color, width=1.5),
        ))
    eq_fig.update_layout(**base_layout("Equity curves: 0 / 5 / 10 / 25 bps"))
    eq_fig.update_yaxes(title_text="growth of $1")
    st.plotly_chart(eq_fig, width='stretch')
