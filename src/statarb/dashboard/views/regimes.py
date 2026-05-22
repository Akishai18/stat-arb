"""Regimes tab: pick a regime; see equity-split + per-signal Sharpe."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from statarb.dashboard.state import DashboardState
from statarb.dashboard.style import NEUTRAL, PRIMARY, base_layout
from statarb.evaluation import evaluate_by_regime

REGIME_LABELS = {
    "vix_high": "VIX (above expanding median = stressed)",
    "energy_bull": "Energy bull/bear (DBE 6m return > 0)",
    "post_2022": "Pre/post 2022 (energy regime shift)",
    "strategy_vol_high": "Strategy realized-vol high vs low",
}


def render(state: DashboardState) -> None:
    st.subheader("Regime breakdown")
    st.caption("How does the headline strategy behave when conditioned on different market environments?")

    choice = st.selectbox(
        "Regime",
        options=list(REGIME_LABELS.keys()),
        format_func=lambda k: REGIME_LABELS[k],
    )
    mask = state.regime_masks[choice]
    headline = state.optimizer_by_cost[state.headline_cost]
    split = evaluate_by_regime(headline, regime_mask=mask, benchmark_returns=state.spy_returns)
    in_r, out_r = split["in_regime"], split["out_regime"]

    cols = st.columns(4)
    cols[0].metric("IN-regime Sharpe", f"{in_r.sharpe:+.2f}")
    cols[1].metric("OUT-regime Sharpe", f"{out_r.sharpe:+.2f}")
    cols[2].metric("IN days", f"{in_r.n_days}")
    cols[3].metric("OUT days", f"{out_r.n_days}")

    # Equity split chart
    mask_aligned = mask.reindex(headline.net_returns.index).fillna(False).astype(bool)
    in_net = headline.net_returns.where(mask_aligned, other=0.0).fillna(0.0)
    out_net = headline.net_returns.where(~mask_aligned, other=0.0).fillna(0.0)
    in_eq = (1.0 + in_net).cumprod()
    out_eq = (1.0 + out_net).cumprod()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=in_eq.index, y=in_eq.values,
        mode="lines", name=f"in {choice}",
        line=dict(color=PRIMARY, width=2),
    ))
    fig.add_trace(go.Scatter(
        x=out_eq.index, y=out_eq.values,
        mode="lines", name=f"out {choice}",
        line=dict(color=NEUTRAL, width=1.5, dash="dash"),
    ))
    fig.update_layout(**base_layout(f"Cumulative contribution: {REGIME_LABELS[choice]}"))
    fig.update_yaxes(title_text="growth of $1 (regime-only days)")
    st.plotly_chart(fig, width='stretch')

    st.divider()

    # Per-signal Sharpe under this regime
    st.markdown("##### Per-signal Sharpe in this regime")
    rows = []
    strategies = {**state.standalone_by_signal,
                  "BASELINE (eq-weight carry+cot)": state.baseline_by_cost[10],
                  "OPTIMIZER (headline)": state.optimizer_by_cost[10]}
    for strat_name, res in strategies.items():
        mask_aligned_loc = mask.reindex(res.net_returns.index)
        split_loc = evaluate_by_regime(res, regime_mask=mask_aligned_loc)
        rows.append({
            "Strategy": strat_name,
            "IN-regime Sharpe": round(split_loc["in_regime"].sharpe, 3),
            "OUT-regime Sharpe": round(split_loc["out_regime"].sharpe, 3),
            "IN days": split_loc["in_regime"].n_days,
            "OUT days": split_loc["out_regime"].n_days,
        })
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
