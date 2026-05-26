"""Overview tab: headline metrics + equity + drawdown + IS/OOS table."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from statarb.dashboard.state import DashboardState, evaluate_walkforward_cached
from statarb.dashboard.style import drawdown_figure, equity_curve_figure


def render(state: DashboardState) -> None:
    st.subheader("Headline strategy")
    st.caption(
        f"Sharpe-weighted blend ({', '.join(state.surviving_signals)}) → "
        f"daily cvxpy QP (λ=50, gross=1.0, net=0.05, pos cap=0.40). "
        f"Backtest spans {state.first_valid.date()} → {state.opt_weights.index.max().date()}."
    )

    bps = st.session_state.get("cost_bps", 10)
    result = state.optimizer_by_cost[bps]
    wf = evaluate_walkforward_cached(result, state.spy_returns)
    full = wf["full"]

    # Metric cards — deltas give Bloomberg-style green/red coloring
    cols = st.columns(6)
    cols[0].metric("SHARPE (FULL)", f"{full.sharpe:+.2f}",
                   delta=f"{full.sharpe:+.2f}", delta_color="normal")
    cols[1].metric("CAGR", f"{full.cagr:+.2%}",
                   delta=f"{full.cagr:+.2%}", delta_color="normal")
    cols[2].metric("ANN VOL", f"{full.ann_vol:.2%}")
    cols[3].metric("MAX DD", f"{full.max_drawdown:.2%}",
                   delta=f"{full.max_drawdown:.2%}", delta_color="normal")
    cols[4].metric("TURNOVER", f"{full.ann_turnover:.1f}x")
    cols[5].metric(
        "ALPHA vs SPY",
        f"{full.alpha_ann:+.2%}" if full.alpha_ann is not None else "n/a",
        delta=(f"{full.alpha_ann:+.2%}" if full.alpha_ann is not None else None),
        delta_color="normal",
    )

    st.divider()

    # Equity curve + drawdown
    spy_cum = (1.0 + state.spy_returns.loc[result.equity_curve.index.min():]).cumprod()
    eq_fig = equity_curve_figure(
        result.equity_curve, spy_cum,
        strategy_label=f"optimizer @ {bps} bps",
        benchmark_label="SPY",
        title="Equity curve",
    )
    st.plotly_chart(eq_fig, width='stretch')

    dd_fig = drawdown_figure(result.equity_curve, title="Drawdown")
    st.plotly_chart(dd_fig, width='stretch')

    # IS / OOS / Full table
    st.subheader("Walk-forward breakdown")
    rows = []
    for window_label, rep in (
        ("In-sample (2011-07 → 2018-12-31)", wf["in_sample"]),
        ("Out-of-sample (2019 →)", wf["out_of_sample"]),
        ("Full window", wf["full"]),
    ):
        rows.append({
            "Window": window_label,
            "Days": rep.n_days,
            "Sharpe": f"{rep.sharpe:+.2f}",
            "CAGR": f"{rep.cagr:+.2%}",
            "Vol": f"{rep.ann_vol:.2%}",
            "Max DD": f"{rep.max_drawdown:.2%}",
            "Beta vs SPY": f"{rep.beta:+.2f}" if rep.beta is not None else "n/a",
            "Alpha (ann)": f"{rep.alpha_ann:+.2%}" if rep.alpha_ann is not None else "n/a",
        })
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
