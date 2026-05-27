# stat-arb

Systematic commodities research platform — a long/short futures portfolio combining curve carry and CFTC managed-money positioning across 13 commodity futures (energy + metals + grains).

> Analyze commodity market data to identify statistical mispricings and exploit them through a systematic long/short portfolio.

**Headline result:** Full-window Sharpe **+1.00** at 10 bps/side, vol **10.8%**, max DD **-11.8%**, alpha vs SPY **+10.5%/yr**, walk-forward-validated 2011–2026. Bootstrap 95% CI **[+0.54, +1.43]** (p < 0.001) excludes zero. After Deflated-Sharpe-Ratio correction for multiple-testing across 25 candidates (Bailey-LdP 2014), DSR = 0.94 — just below the strict 95% bar. Sharpe range under leave-one-commodity-out and alternate-split sensitivity sweeps: **[+0.65, +1.27]**, comfortably positive in all 27 perturbations.

A 5-commodity (energy-only) earlier version produced Sharpe +0.28 with CI straddling zero. Expanding to 13 commodities (Phase A1) was the breakthrough that made the signal statistically real. Honest details in [`reports/FINAL.md`](./reports/FINAL.md).

The complete project narrative is in [`reports/FINAL.md`](./reports/FINAL.md). The phased plan is in [`PLAN.md`](./PLAN.md). Per-phase reports are `01_*` through `09_*` under [`reports/`](./reports/). The forward-looking roadmap (Layer A → Layer B live trading) is in [`ROADMAP.md`](./ROADMAP.md).

## Quickstart

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
# Install with all extras (dev tools + cvxpy + streamlit dashboard)
uv sync --extra dev --extra opt --extra dashboard

# (Optional) Free EIA API key for the inventory signal
# Register: https://www.eia.gov/opendata/register.php
# Add to .env at the repo root:
#   EIA_API_KEY=your_key_here
# (the project loads .env automatically via python-dotenv)

# Ingest data (one-time, ~1 minute)
uv run python -m statarb.cli.ingest         # yfinance ETF + futures
uv run python -m statarb.cli.ingest_macro   # CFTC always; EIA if key set

# Launch the interactive dashboard
uv run streamlit run scripts/dashboard.py

# Reproduce all phase reports + the final synthesis
uv run python scripts/run_momentum.py                  # Phase 3 (mom)
uv run python scripts/run_reversal_and_combo.py        # Phase 4 (reversal + combine)
uv run python scripts/run_carry_and_futures.py         # Phase 5 (carry)
uv run python scripts/run_macro_signals.py             # Phase 6 (COT + EIA inventory)
uv run python scripts/run_optimization.py              # Phase 7 (cvxpy optimizer)
uv run python scripts/run_final_evaluation.py          # Phase 8 + A1 + A3 (13-comm + bootstrap + DSR)
uv run python scripts/run_walkforward.py               # Phase A2 (annual + walk-forward)
uv run python scripts/run_sensitivity.py               # Phase A6 (27 sensitivity sweeps)
uv run python scripts/run_calendar_carry_validation.py # Phase A4 (carry-proxy validation)

# Verify the pipeline is intact
uv run pytest    # 176 tests
uv run ruff check src tests scripts
```

## Interactive dashboard

Bloomberg-terminal-styled Streamlit + Plotly app with 7 tabs:

- **Overview** — headline metrics, equity curve vs SPY, drawdown, IS/OOS/Full table
- **Today** — latest signal scores per asset, current optimizer weights, rebalance diff
- **Signals** — standalone performance table, correlation matrix, per-regime Sharpe heatmap
- **Portfolio** — weight time series, gross/net exposure, daily turnover, position-cap utilization
- **Costs** — master cost-sensitivity table + Sharpe-vs-cost line chart
- **Regimes** — selector for VIX / energy / period / strategy-vol regimes with equity-split chart
- **About** — methodology, links to phase reports, reproducibility

Heavy computations (signal panels, optimizer path, regime masks) are cached once per session via `@st.cache_data` so navigation between tabs is instant.

## Layout

```
src/statarb/
  data/         # loaders, point-in-time price access, EIA + CFTC ingestion
  signals/      # momentum, reversal, carry, COT, inventory, combine, sharpe-weighted blend
  backtest/     # vectorized no-lookahead engine + result dataclass
  portfolio/    # eq-weight quantile + cvxpy optimizer + rolling covariance
  costs/        # linear + zero cost models
  evaluation/   # metrics, walk-forward, regimes, plots
  dashboard/    # streamlit app + cached state + 7 view modules
  cli/          # ingestion entrypoints
scripts/        # per-phase runners + dashboard launcher
tests/          # 176 passing tests
reports/        # phase reports + FINAL.md + charts
```

## Status

**All 9 phases complete.** See `reports/FINAL.md` for the synthesis writeup.

## Stack

- Python 3.11+, `uv` for package management
- `pandas`, `numpy`, `scipy`, `statsmodels` for data + metrics
- `cvxpy` + `OSQP` for the portfolio optimizer
- `yfinance` + `requests` for data ingestion
- `streamlit` + `plotly` for the interactive dashboard
- `pytest` + `ruff` for tests + lint
- `python-dotenv` for `.env` loading
