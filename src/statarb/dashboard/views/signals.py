"""Signals tab: standalone performance, correlations, regime contribution."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from statarb.dashboard.state import DashboardState, evaluate_cached
from statarb.dashboard.style import base_layout
from statarb.evaluation import evaluate_by_regime


def render(state: DashboardState) -> None:
    st.subheader("Signal diagnostics")
    st.caption("Each signal evaluated standalone as a top-40% / bottom-40% long-short quantile portfolio at 10 bps. The optimizer below uses the surviving-positive-Sharpe subset.")

    # Standalone performance table
    rows = []
    for name, res in state.standalone_by_signal.items():
        rep = evaluate_cached(res, state.spy_returns)
        rows.append({
            "Signal": name,
            "IS Sharpe": round(state.is_sharpes[name], 3),
            "Full Sharpe": round(rep.sharpe, 3),
            "Full CAGR": f"{rep.cagr:+.2%}",
            "Vol": f"{rep.ann_vol:.2%}",
            "Max DD": f"{rep.max_drawdown:.2%}",
            "Turnover/yr": f"{rep.ann_turnover:.1f}x",
            "Used in blend?": "YES" if name in state.surviving_signals else "no",
        })
    df = pd.DataFrame(rows).sort_values("IS Sharpe", ascending=False)
    st.dataframe(df, width='stretch', hide_index=True)

    st.divider()

    # Net-return correlation heatmap
    st.markdown("##### Signal correlation (full window, 10 bps)")
    returns_by_name = {n: r.net_returns for n, r in state.standalone_by_signal.items()}
    corr_df = pd.DataFrame(returns_by_name).dropna(how="any").corr().round(3)
    corr_fig = go.Figure(data=go.Heatmap(
        z=corr_df.values,
        x=corr_df.columns, y=corr_df.index,
        colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
        text=corr_df.values.round(2), texttemplate="%{text}",
        textfont=dict(size=12),
    ))
    corr_fig.update_layout(**base_layout("Net-return correlation"))
    corr_fig.update_layout(height=420)
    st.plotly_chart(corr_fig, width='stretch')

    st.divider()

    # Per-signal Sharpe by regime (heatmap)
    st.markdown("##### Per-signal Sharpe by regime (in-regime cells)")
    regime_rows = []
    strategies = {**state.standalone_by_signal,
                  "BASELINE (eq-weight carry+cot)": state.baseline_by_cost[10],
                  "OPTIMIZER (headline)": state.optimizer_by_cost[10]}
    for strat_name, res in strategies.items():
        for regime_name, mask in state.regime_masks.items():
            mask_aligned = mask.reindex(res.net_returns.index)
            split = evaluate_by_regime(res, regime_mask=mask_aligned)
            regime_rows.append({
                "strategy": strat_name,
                "regime": regime_name,
                "sharpe": split["in_regime"].sharpe,
            })
    rg_df = pd.DataFrame(regime_rows)
    pivot = rg_df.pivot(index="strategy", columns="regime", values="sharpe").round(2)
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns, y=pivot.index,
        colorscale="RdBu", zmid=0, zmin=-1.5, zmax=1.5,
        text=pivot.values.round(2), texttemplate="%{text}",
        textfont=dict(size=11),
    ))
    fig.update_layout(**base_layout("In-regime Sharpe by strategy x regime"))
    fig.update_layout(height=420)
    st.plotly_chart(fig, width='stretch')
