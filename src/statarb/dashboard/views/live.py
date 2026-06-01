"""Live tab: the paper-trading book as it accumulates day by day.

Unlike every other tab (which renders the cached backtest), this reads the
live `LivePortfolio` state straight off disk on each rerun -- the book changes
once per trading day as `scripts/daily_pulse.py` advances it, so caching it
would just show a stale equity curve. The trace starts flat and is genuinely
out-of-sample: it should track the backtested headline going forward.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from statarb.dashboard.state import DashboardState
from statarb.dashboard.style import (
    AMBER_DIM,
    drawdown_figure,
    equity_curve_figure,
)
from statarb.live.portfolio import LivePortfolio

_LEDGER_DISPLAY = {
    "net_return": "Net",
    "gross_return": "Gross",
    "cost": "Cost",
    "turnover": "Turnover",
    "equity": "Equity",
    "notional": "Notional ($)",
    "gross_exposure": "Gross exp",
    "net_exposure": "Net exp",
    "n_long": "# Long",
    "n_short": "# Short",
}


def _empty_state() -> None:
    st.subheader("Live paper book — not started yet")
    st.caption(
        "The paper trace is empty. It starts flat on the first pulse — a genuine "
        "out-of-sample record with no back-seeded history."
    )
    st.markdown(
        "**Start it (records today as day 1):**\n"
        "```\nuv run python scripts/daily_pulse.py\n```\n"
        "**Then schedule it (runs every weekday, 5pm):**\n"
        "```\ncp scripts/launchd/com.statarb.dailypulse.plist ~/Library/LaunchAgents/\n"
        "launchctl load ~/Library/LaunchAgents/com.statarb.dailypulse.plist\n```"
    )


def render(state: DashboardState) -> None:
    port = LivePortfolio.load_or_create()
    ledger = port.ledger

    if ledger.empty:
        _empty_state()
        return

    ledger = ledger.sort_index()
    equity = ledger["equity"]
    last = ledger.iloc[-1]
    start_date, end_date = equity.index.min(), equity.index.max()
    total_return = float(equity.iloc[-1]) - 1.0
    max_dd = float((equity / equity.cummax() - 1.0).min())

    st.subheader(f"Live paper book — {start_date.date()} → {end_date.date()}")
    st.caption(
        f"${port.initial_notional:,.0f} paper notional, {port.cost_bps:.0f} bps/side. "
        f"Day-by-day restatement of the validated headline strategy "
        f"({len(ledger)} trading day{'s' if len(ledger) != 1 else ''} recorded). "
        "Should track the backtest going forward."
    )

    # --- headline cards ---
    cols = st.columns(6)
    cols[0].metric("EQUITY", f"{equity.iloc[-1]:.4f}")
    cols[1].metric("NOTIONAL", f"${last['notional']:,.0f}")
    cols[2].metric("TOTAL RETURN", f"{total_return:+.2%}",
                   delta=f"{total_return:+.2%}", delta_color="normal")
    cols[3].metric("LATEST DAY", f"{last['net_return']:+.3%}",
                   delta=f"{last['net_return']:+.3%}", delta_color="normal")
    cols[4].metric("MAX DD", f"{max_dd:.2%}",
                   delta=f"{max_dd:.2%}", delta_color="normal")
    cols[5].metric("DAYS", f"{len(ledger)}")

    # --- staleness banner ---
    stale_days = (pd.Timestamp.now().normalize() - end_date).days
    if stale_days > 5:
        st.warning(
            f"Last recorded day is {end_date.date()} — {stale_days} days ago. "
            "The daily pulse may not be running; check `data/live/cron.log`."
        )

    st.divider()

    # --- equity curve (paper book vs SPY over the live window) ---
    spy = state.spy_returns.loc[start_date:end_date]
    spy_cum = (1.0 + spy).cumprod().reindex(equity.index).ffill() if len(spy) else None
    eq_fig = equity_curve_figure(
        equity, spy_cum,
        strategy_label="paper book (net)",
        benchmark_label="SPY",
        title="PAPER EQUITY (LIVE)",
    )
    st.plotly_chart(eq_fig, width="stretch")

    if len(ledger) >= 2:
        st.plotly_chart(drawdown_figure(equity, title="PAPER DRAWDOWN"), width="stretch")

    st.divider()

    # --- current book ---
    st.markdown("##### Current exposure")
    ec = st.columns(4)
    ec[0].metric("Gross", f"{last['gross_exposure']:.2f}")
    ec[1].metric("Net", f"{last['net_exposure']:+.3f}")
    ec[2].metric("# Long", f"{int(last['n_long'])}")
    ec[3].metric("# Short", f"{int(last['n_short'])}")

    if not port.targets.empty:
        latest_tgt = port.targets.loc[port.targets.index.max()]
        held = latest_tgt[latest_tgt.abs() > 1e-9].sort_values(ascending=False)
        st.markdown("##### Positions held into the next session")
        st.dataframe(
            pd.DataFrame({"Asset": held.index, "Weight": held.round(4).values}),
            width="stretch", hide_index=True,
        )

    st.divider()

    # --- ledger ---
    st.markdown("##### Daily ledger")
    show = ledger[list(_LEDGER_DISPLAY)].rename(columns=_LEDGER_DISPLAY).copy()
    for col in ("Net", "Gross", "Cost"):
        show[col] = show[col].map("{:+.4%}".format)
    show["Turnover"] = show["Turnover"].map("{:.3f}".format)
    show["Equity"] = show["Equity"].map("{:.4f}".format)
    show["Notional ($)"] = show["Notional ($)"].map("{:,.0f}".format)
    show["Gross exp"] = show["Gross exp"].map("{:.3f}".format)
    show["Net exp"] = show["Net exp"].map("{:+.3f}".format)
    show["# Long"] = show["# Long"].astype(int)
    show["# Short"] = show["# Short"].astype(int)
    show.insert(0, "Date", [d.date() for d in ledger.index])
    st.dataframe(show.iloc[::-1], width="stretch", hide_index=True)

    st.caption(
        f"<span style='color:{AMBER_DIM}'>State on disk: data/live/ "
        "(ledger.parquet, targets.parquet, meta.json, log.txt). Re-reads on each "
        "page refresh — rerun the tab after a pulse to see the new day.</span>",
        unsafe_allow_html=True,
    )
