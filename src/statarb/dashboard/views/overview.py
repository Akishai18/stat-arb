"""Overview tab: headline metrics + equity + drawdown + IS/OOS table.

Shows the BASELINE strategy (equal-weight quantile carry+cot) because that
is the deployable headline — Phase 7's cvxpy optimizer was a documented
underperformer on the wider 13-commodity universe. See FINAL.md.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from statarb.dashboard.state import DashboardState, evaluate_walkforward_cached
from statarb.dashboard.style import drawdown_figure, equity_curve_figure


def render(state: DashboardState) -> None:
    st.subheader("Headline strategy")
    st.caption(
        f"Equal-weight cross-sectional z-score blend of {', '.join(state.surviving_signals)}, "
        f"long top 40% / short bottom 40%, dollar-neutral, daily rebalance. "
        f"Backtest spans {state.first_valid.date()} → {state.opt_weights.index.max().date()}."
    )

    bps = st.session_state.get("cost_bps", 10)
    # Headline = BASELINE (FINAL.md). The optimizer is shown alongside for context
    # in the cost-sensitivity section below.
    result = state.baseline_by_cost[bps]
    wf = evaluate_walkforward_cached(result, state.spy_returns)
    full = wf["full"]
    opt_full = evaluate_walkforward_cached(state.optimizer_by_cost[bps], state.spy_returns)["full"]

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

    st.caption(
        f"For context: the Phase 7 cvxpy optimizer (locked λ=50 hyperparameters) "
        f"produces Sharpe {opt_full.sharpe:+.2f} on the same universe — a documented "
        f"Markowitz overfit, replaced by this simpler baseline. See `reports/FINAL.md`."
    )

    st.divider()

    # Equity curve + drawdown
    spy_cum = (1.0 + state.spy_returns.loc[result.equity_curve.index.min():]).cumprod()
    eq_fig = equity_curve_figure(
        result.equity_curve, spy_cum,
        strategy_label=f"baseline @ {bps} bps",
        benchmark_label="SPY",
        title="EQUITY CURVE",
    )
    st.plotly_chart(eq_fig, width='stretch')

    dd_fig = drawdown_figure(result.equity_curve, title="DRAWDOWN")
    st.plotly_chart(dd_fig, width='stretch')

    # IS / OOS / Full table
    st.subheader("Walk-forward breakdown")
    rows = []
    for window_label, rep in (
        ("IN-SAMPLE (2011-07 → 2018-12-31)", wf["in_sample"]),
        ("OUT-OF-SAMPLE (2019 →)", wf["out_of_sample"]),
        ("FULL WINDOW", wf["full"]),
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
