# Stat-Arb: Implementation Plan

## One-line project description
> Analyze commodity market data to identify statistical mispricings and exploit them through a systematic long/short portfolio.

## Scope decisions (locked)
- **Asset focus:** energy commodities — WTI, Brent, natural gas, gasoline, heating oil. Start with ETF proxies, upgrade to futures.
- **Strategy class:** time-series momentum + short-term reversal + curve carry + (later) inventory/positioning signals. Honestly framed as systematic energy / CTA-style, *not* classical wide-cross-section stat arb, because the universe is small.
- **Target audience:** all three quant tracks — research, dev, trading. The project must hit each:
  - **Research:** clean hypotheses, walk-forward validation, honest evaluation including failure modes.
  - **Dev:** modular Python package, tests, type hints, reproducible pipeline.
  - **Trading:** cost sensitivity, risk controls, paper-trading hook.
- **Budget:** free data sources first (yfinance, EIA, CFTC). Paid (Nasdaq Data Link / Polygon) only if a phase blocks on it.
- **No SignalM dependency.** Regime analysis is built standalone inside this project.

## Tech stack
- **Language:** Python 3.11+
- **Package manager:** `uv` (fast, modern; or `poetry` if preferred)
- **Core libs:** `pandas`, `numpy`, `scipy`, `statsmodels`
- **Optimization:** `cvxpy` (Phase 7)
- **Data:** `yfinance` (prices), `requests` for EIA + CFTC raw downloads
- **Storage:** Parquet files on disk (no DB until needed)
- **Testing:** `pytest`
- **Lint/format:** `ruff`
- **Plots / reports:** `matplotlib` + `quantstats` (sanity check only — roll our own metrics for the headline numbers)
- **Notebooks:** `jupyter` for exploration only; production code lives in the package
- **Dashboard (Phase 9, optional):** `streamlit` first; only escalate to FastAPI + Next.js if time allows

## Repo structure
```
stat-arb/
  pyproject.toml
  README.md
  PLAN.md
  data/
    raw/            # immutable downloads (gitignored)
    processed/      # cleaned parquet (gitignored)
  src/statarb/
    data/           # loaders, cleaners, point-in-time enforcement
    signals/        # signal definitions, each as a pure function
    backtest/       # engine, position tracking, returns
    portfolio/      # weighting + optimization
    costs/          # cost models (linear, sqrt-impact)
    evaluation/     # metrics, walk-forward, regime split
    cli/            # ingestion + run scripts
  notebooks/        # exploration only, not the source of truth
  tests/
  reports/          # final writeups + charts
  scripts/          # one-off data downloads
```

---

## Phased implementation

Each phase has: **Goal**, **Deliverables**, **Done when**, **Notes**. Phases are sequential — don't start phase N+1 until N's "done when" is met.

### Phase 0 — Foundation
**Goal:** Make the repo a real Python project, not a scratch folder.

**Deliverables:**
- `pyproject.toml` with dependencies pinned via `uv`
- `src/statarb/` package skeleton (empty modules with docstrings)
- `tests/` with one trivial passing test
- `.gitignore` (data/, .venv/, __pycache__/, .ipynb_checkpoints/)
- `ruff` config + pre-commit hook
- README updated with quickstart

**Done when:** `uv run pytest` passes and `uv run python -c "import statarb"` works.

---

### Phase 1 — Data layer (ETF proxies)
**Goal:** A clean, point-in-time-safe data layer for energy ETFs.

**Deliverables:**
- Loader for daily OHLCV via `yfinance` for: USO, BNO, UNG, UGA, UHN, DBE (+ SPY as benchmark, ^VIX as regime context)
- Caching: raw downloads → `data/raw/<ticker>.parquet`; cleaned panel → `data/processed/prices.parquet`
- Adjusted close + simple returns + log returns
- A `PriceData` class that exposes prices/returns *as-of* a given date (no lookahead)
- Unit test: asking for data "as of 2020-06-15" must return nothing dated after that

**Done when:** A single function call returns a clean, gap-handled, point-in-time-correct returns panel for the energy ETF universe from 2010+.

**Notes:**
- ETF proxies bleed from contango (especially USO, UNG). This is a **feature** of the project, not a bug — we'll discuss it in the writeup and it motivates the futures upgrade in Phase 5.

---

### Phase 2 — Backtest engine MVP
**Goal:** A vectorized backtester that doesn't cheat.

**Deliverables:**
- `Signal` protocol: `prices_panel → daily score panel` (one score per asset per day)
- `Backtester` class:
  - Input: signal scores, prices, cost model
  - Convention: **signal computed using data up to t's close → trade at t+1 open → hold until next rebalance**
  - Output: positions, daily portfolio returns, turnover series
- Equal-weight long/short construction (long top half, short bottom half; later top/bottom decile)
- Linear transaction cost model (bps per dollar traded)
- Tests:
  - Synthetic price series with known signal → known return (proves no lookahead)
  - Zero-signal portfolio → near-zero return (minus costs)

**Done when:** Backtester runs end-to-end on a constant random signal and produces a plausible equity curve + turnover number.

---

### Phase 3 — First signal: time-series momentum
**Goal:** Get *one* signal to a fully evaluated state before adding more.

**Deliverables:**
- `signals/momentum.py`: 12-1 momentum (12-month return excluding most recent month). Also parameterize lookback.
- Backtest on the ETF universe
- Evaluation suite (`evaluation/metrics.py`):
  - CAGR, annualized vol, Sharpe, Sortino
  - Max drawdown + drawdown duration
  - Hit rate (fraction of months positive)
  - Turnover (annualized)
  - Beta vs SPY, alpha vs SPY
- Walk-forward split: in-sample (2010–2018) for parameter choice, out-of-sample (2019–today) for honest reporting
- Cost sensitivity panel: equity curves at 0 / 5 / 10 / 25 bps
- One markdown report: `reports/01_momentum.md` — hypothesis, results, what worked, what didn't

**Done when:** You can answer "does pure momentum work on energy ETFs after costs?" with a number + chart + paragraph.

---

### Phase 4 — Second signal: short-term reversal + combination
**Goal:** Add a second signal, then learn how to combine.

**Deliverables:**
- `signals/reversal.py`: 5-day reversal (negative of trailing 5-day return)
- Run reversal standalone with same evaluation suite
- Signal combination:
  - Cross-sectional z-score each signal
  - Combined score: equal weight at first, then alpha-proportional
- **Signal attribution:** decompose combined P&L into per-signal contribution; report signal-pair correlation
- `reports/02_reversal_and_combo.md`

**Done when:** You can answer "do momentum and reversal capture different alpha, and does combining them help after costs?"

---

### Phase 5 — Upgrade to futures + carry signal
**Goal:** Move from ETFs to continuous futures so we can compute curve carry. This is the biggest data-engineering jump in the project.

**Deliverables:**
- Continuous futures construction for CL (WTI), BZ (Brent), NG (nat gas), RB (gasoline), HO (heating oil):
  - Free path: yfinance `=F` tickers (front month, auto-rolled — limited but workable as MVP)
  - Better path: download CME historical settlements via Nasdaq Data Link or directly; build panama-adjusted continuous series
  - Document the roll method explicitly — this is an interview talking point
- Front-month + second-month series per commodity
- `signals/carry.py`: carry = (front - second) / second, annualized
- Re-run momentum + reversal + carry on the futures universe
- `reports/03_futures_and_carry.md`

**Done when:** A 3-signal backtest runs on continuous futures and the carry signal is interpretable (backwardation vs contango).

**Notes:**
- This is the phase most likely to need paid data. If free continuous-futures construction proves too painful, paying a one-time fee for Nasdaq Data Link historical futures is acceptable. Decide at phase start.

---

### Phase 6 — Exogenous data: EIA inventories + CFTC COT
**Goal:** Add signals a pure-price project can't have. This is the differentiator.

**Deliverables:**
- EIA weekly petroleum data ingestion (free API key) — crude stocks, gasoline stocks, distillate stocks
- Inventory surprise = actual change vs 5-year seasonal average
- CFTC Commitments of Traders ingestion (free download) — managed money + commercial net positions per commodity
- COT positioning z-score (3-year rolling window)
- New signals: `inventory_surprise`, `cot_positioning`
- Each evaluated standalone, then integrated into combined alpha
- **Critical:** point-in-time release dates matter — EIA Wednesday release, COT Friday release. No backtest trades on data before its release timestamp.
- `reports/04_macro_signals.md`

**Done when:** Inventory + positioning signals run with correct release-date alignment and have standalone Sharpe numbers.

---

### Phase 7 — Portfolio construction upgrade
**Goal:** Move from naive equal-weight to risk-aware portfolio construction.

**Deliverables:**
- Volatility targeting: scale total portfolio to a target annualized vol (e.g. 10%)
- Per-asset vol scaling: position size proportional to `alpha_score / vol`
- `cvxpy` optimizer:
  - Objective: `alpha · w - λ · wᵀΣw - cost(turnover)`
  - Constraints: per-asset cap, gross exposure cap, net exposure ≈ 0, turnover cap
- Sensitivity: sweep `λ` and turnover cap, plot Sharpe surface
- `reports/05_portfolio_construction.md`

**Done when:** Optimized portfolio's net exposure stays bounded, turnover respects the cap, and Sharpe is reported alongside naive equal-weight as a baseline.

---

### Phase 8 — Final evaluation + regime analysis
**Goal:** The "would I deploy this?" question.

**Deliverables:**
- Walk-forward out-of-sample equity curve (final headline chart)
- Regime split:
  - VIX high vs low
  - Energy bull vs bear (trailing 6m USO return positive/negative)
  - High vs low realized vol of strategy itself
  - Pre/post 2022 (energy regime shift)
- Per-signal contribution table across regimes
- Cost-sensitivity master table: Sharpe at 0/5/10/25 bps × naive/optimized
- Final writeup `reports/FINAL.md`:
  - Hypothesis
  - Methodology
  - Headline results
  - What didn't work (be honest — recruiters love this)
  - Limitations (survivorship, lookback bias from parameter choices, data quality)
  - What I'd do with more time

**Done when:** A reader who has never seen the code can read `reports/FINAL.md` and understand what was built, what worked, and what the limits are.

---

### Phase 9 — (Optional) Paper trading dashboard
**Goal:** Make it feel production-ready. Only after Phase 8 is done.

**Deliverables:**
- `streamlit` app:
  - Daily refresh: pull latest prices + EIA + COT
  - Show current signal scores and target positions
  - Track paper P&L since launch vs SPY and DBC
  - Drawdown / exposure / turnover charts
- Optional escalation: FastAPI backend + Next.js frontend if recruiting for full-stack-leaning quant-dev roles

**Done when:** The app runs locally, updates daily, and a screenshot makes it into the README.

---

## Risk register
Things that have killed projects like this before — keep an eye out:
- **Lookahead bias.** Mitigation: enforce as-of access in `PriceData`, write tests around it, never `.shift(-1)` anything.
- **Survivorship in the universe.** Mitigation: fixed universe defined at project start, documented. Energy futures barely change so this is small.
- **Overfitting to ETF era.** Mitigation: walk-forward, OOS split, don't tune parameters on the OOS window.
- **Free futures data quality.** Mitigation: explicitly document the roll method; budget for paid data if Phase 5 blocks.
- **Scope creep into dashboard.** Mitigation: Phase 9 is *optional* and gated on Phase 8 being done.
- **Notebook sprawl.** Mitigation: notebooks are exploration only; once a finding holds up, it gets ported into the package + a test.

---

## Resume framing (targets for the final writeup)

**Research angle:**
> Built a systematic energy-commodities research platform combining time-series momentum, short-term reversal, curve carry, EIA inventory surprises, and CFTC positioning signals; evaluated long/short portfolios across market regimes with walk-forward validation and cost sensitivity.

**Engineering angle:**
> Designed a modular, point-in-time-safe Python backtesting engine with vectorized portfolio construction, cvxpy-based optimization under turnover and exposure constraints, and a Streamlit paper-trading dashboard pulling live EIA, CFTC, and price data.

**Trading angle:**
> Implemented risk-aware portfolio construction with volatility targeting, turnover-bounded optimization, and slippage-sensitivity analysis to evaluate strategy robustness under realistic trading frictions across crude oil, natural gas, and refined products.

All three are true descriptions of the same project — the emphasis shifts per application.

---

## Immediate next step

Phase 0. Decide on `uv` vs `poetry`, then scaffold the package. Everything else flows from a clean foundation.
