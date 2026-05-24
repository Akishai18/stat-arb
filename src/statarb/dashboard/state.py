"""Cached data and pipeline computations for the dashboard.

Every expensive operation is wrapped in @st.cache_data so it runs once
per process. Modifying constants in this file invalidates the cache
automatically (Streamlit hashes module source).

State design: each loader returns a frozen dataclass. The top-level
`build_state()` aggregates everything into a single `DashboardState`
object that views consume via `state = build_state()`.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from statarb.backtest import Backtester
from statarb.backtest.result import BacktestResult
from statarb.costs import LinearCostModel
from statarb.data import (
    ETF_FUTURES_PAIRS,
    PriceData,
    all_tradable_futures,
    mask_known_anomalies,
)
from statarb.data.cftc import load_cot_panel
from statarb.data.eia import EIAKeyMissing, load_eia_panel
from statarb.evaluation import (
    DEFAULT_IS_END,
    evaluate,
    evaluate_walkforward,
    period_regime,
    split_in_out_sample,
    strategy_vol_regime,
    trailing_return_regime,
    vix_regime,
)
from statarb.portfolio import (
    long_short_quantile_weights,
    optimize_path,
    rolling_covariance,
)
from statarb.signals import (
    combine as eq_combine,
)
from statarb.signals import (
    cot_positioning,
    inventory_surprise,
    momentum,
    realized_carry,
    reversal,
    sharpe_weighted_combine,
)

# --- Locked Phase 7 hyperparameters ---
MOM_LOOKBACK = 252
MOM_SKIP = 21
REV_LOOKBACK = 5
CARRY_LOOKBACK = 21
COT_LOOKBACK_WEEKS = 156
INVENTORY_SEASONAL_YEARS = 5
COV_LOOKBACK = 63

GROSS_CAP = 1.0
NET_CAP = 0.05
POSITION_CAP = 0.40
RISK_AVERSION = 50.0
TURNOVER_CAP = None
LONG_Q = 0.4
SHORT_Q = 0.4
COST_LEVELS_BPS = (0, 5, 10, 25)
HEADLINE_COST_BPS = 10


@dataclass(frozen=True)
class DashboardState:
    # data
    prices: PriceData
    adj_clean: pd.DataFrame
    futures: list[str]
    fut_adj: pd.DataFrame
    spy_returns: pd.Series
    # signals (full panels, indexed by daily date)
    signals: dict[str, pd.DataFrame]
    is_sharpes: dict[str, float]
    surviving_signals: list[str]
    first_valid: pd.Timestamp
    # weights + backtest results
    alpha_panel: pd.DataFrame
    opt_weights: pd.DataFrame
    optimizer_by_cost: dict[int, BacktestResult]
    baseline_by_cost: dict[int, BacktestResult]
    standalone_by_signal: dict[str, BacktestResult]
    # regime masks (aligned to optimizer headline result index)
    regime_masks: dict[str, pd.Series]
    # convenience
    has_inventory: bool
    headline_cost: int = HEADLINE_COST_BPS


@st.cache_data(show_spinner="Loading price data...")
def _load_prices() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    raw = PriceData.load()
    adj_clean = mask_known_anomalies(raw.adj_close())
    spy = PriceData(adj_clean).returns()["SPY"]
    fut_adj = adj_clean[all_tradable_futures()]
    return adj_clean, spy, fut_adj


@st.cache_data(show_spinner="Loading COT panel...")
def _load_cot_panel_cached() -> pd.DataFrame:
    return load_cot_panel()


@st.cache_data(show_spinner="Loading EIA inventory panel...")
def _load_eia_panel_cached() -> pd.DataFrame | None:
    try:
        return load_eia_panel()
    except (FileNotFoundError, EIAKeyMissing):
        return None


@st.cache_data(show_spinner="Computing signals...")
def _compute_signals(
    adj_clean_key: int,  # cache key (hash of index range/shape)
) -> tuple[dict[str, pd.DataFrame], bool, pd.Timestamp]:
    adj_clean, _, fut_adj = _load_prices()
    daily_index = adj_clean.index

    mom_score = momentum(fut_adj, lookback=MOM_LOOKBACK, skip=MOM_SKIP)
    rev_score = reversal(fut_adj, lookback=REV_LOOKBACK)

    carry_raw = realized_carry(adj_clean, pairs=ETF_FUTURES_PAIRS, lookback=CARRY_LOOKBACK)
    carry_score = pd.DataFrame(
        index=mom_score.index, columns=mom_score.columns, dtype=float
    )
    for c in carry_raw.columns:
        if c in carry_score.columns:
            carry_score[c] = carry_raw[c]

    cot_panel = _load_cot_panel_cached()
    cot_score = cot_positioning(
        cot_panel, lookback_weeks=COT_LOOKBACK_WEEKS, target_index=daily_index
    ).reindex(columns=mom_score.columns)

    eia_panel = _load_eia_panel_cached()
    if eia_panel is not None:
        inv_score = inventory_surprise(
            eia_panel,
            seasonal_years=INVENTORY_SEASONAL_YEARS,
            target_index=daily_index,
        ).reindex(columns=mom_score.columns)
    else:
        inv_score = None

    signals: dict[str, pd.DataFrame] = {
        "momentum": mom_score,
        "reversal": rev_score,
        "carry": carry_score,
        "cot": cot_score,
    }
    has_inventory = inv_score is not None
    if has_inventory:
        signals["inventory"] = inv_score

    cand = [
        mom_score.index[mom_score.notna().sum(axis=1) >= 4][0],
        cot_score.index[cot_score.notna().sum(axis=1) >= 3][0],
    ]
    if has_inventory:
        cand.append(inv_score.index[inv_score.notna().sum(axis=1) >= 3][0])
    first_valid = max(cand)
    return signals, has_inventory, first_valid


def _build_q(score: pd.DataFrame, first_valid: pd.Timestamp) -> pd.DataFrame:
    return long_short_quantile_weights(
        score.loc[first_valid:],
        long_quantile=LONG_Q,
        short_quantile=SHORT_Q,
        gross_leverage=1.0,
    )


def _run(prices: PriceData, weights: pd.DataFrame, bps: int) -> BacktestResult:
    return Backtester(prices, LinearCostModel(bps_per_side=bps)).run(weights)


def _is_sharpe(returns: pd.Series) -> float:
    is_part, _ = split_in_out_sample(returns, in_sample_end=DEFAULT_IS_END)
    r = is_part.dropna()
    if len(r) < 2:
        return 0.0
    s = r.std(ddof=1)
    if s == 0:
        return 0.0
    return float(r.mean() / s * (252**0.5))


@st.cache_data(show_spinner="Backtesting standalone signals...")
def _standalone_backtests(
    _adj_key: int,
) -> tuple[dict[str, BacktestResult], dict[str, float]]:
    adj_clean, _, _ = _load_prices()
    prices = PriceData(adj_clean)
    signals, _, first_valid = _compute_signals(_adj_key)
    results: dict[str, BacktestResult] = {}
    sharpes: dict[str, float] = {}
    for name, sc in signals.items():
        res = _run(prices, _build_q(sc, first_valid), HEADLINE_COST_BPS)
        results[name] = res
        sharpes[name] = _is_sharpe(res.net_returns)
    return results, sharpes


@st.cache_data(show_spinner="Optimizing portfolio (this runs once per session)...")
def _optimizer_backtests(
    _adj_key: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, BacktestResult], dict[int, BacktestResult]]:
    adj_clean, _, _ = _load_prices()
    prices = PriceData(adj_clean)
    signals, _has_inv, first_valid = _compute_signals(_adj_key)
    _standalone, is_sharpes = _standalone_backtests(_adj_key)

    aligned = {n: s.loc[first_valid:] for n, s in signals.items()}
    alpha = sharpe_weighted_combine(aligned, is_sharpes=is_sharpes)

    futures = all_tradable_futures()
    returns_panel = prices.returns()[futures]
    cov_cache = rolling_covariance(returns_panel, lookback=COV_LOOKBACK, min_periods=20)
    opt_weights = optimize_path(
        alpha,
        returns_panel,
        gross_cap=GROSS_CAP,
        net_cap=NET_CAP,
        position_cap=POSITION_CAP,
        risk_aversion=RISK_AVERSION,
        cost_bps_per_side=HEADLINE_COST_BPS,
        turnover_cap=TURNOVER_CAP,
        cov_cache=cov_cache,
    )

    # Baseline: equal-weight carry+cot
    baseline_alpha = eq_combine(
        {"carry": signals["carry"].loc[first_valid:], "cot": signals["cot"].loc[first_valid:]}
    )
    baseline_weights = long_short_quantile_weights(
        baseline_alpha, long_quantile=LONG_Q, short_quantile=SHORT_Q, gross_leverage=1.0,
    )

    optimizer_by_cost = {
        bps: _run(prices, opt_weights, bps) for bps in COST_LEVELS_BPS
    }
    baseline_by_cost = {
        bps: _run(prices, baseline_weights, bps) for bps in COST_LEVELS_BPS
    }
    return alpha, opt_weights, optimizer_by_cost, baseline_by_cost


@st.cache_data(show_spinner="Computing regime masks...")
def _build_regime_masks(_adj_key: int) -> dict[str, pd.Series]:
    adj_clean, _, _ = _load_prices()
    prices = PriceData(adj_clean)
    _alpha, _ow, optimizer_by_cost, _ = _optimizer_backtests(_adj_key)
    headline = optimizer_by_cost[HEADLINE_COST_BPS]
    masks = {
        "vix_high": vix_regime(prices.adj_close()["^VIX"]),
        "energy_bull": trailing_return_regime(prices.adj_close()["DBE"], lookback=126),
        "post_2022": period_regime(adj_clean.index, split_date="2021-12-31"),
        "strategy_vol_high": strategy_vol_regime(headline.net_returns, lookback=63),
    }
    return {k: v.reindex(headline.net_returns.index) for k, v in masks.items()}


def build_state() -> DashboardState:
    """Build the full state. Heavy computations are cached."""
    adj_clean, spy, fut_adj = _load_prices()
    adj_key = int(adj_clean.shape[0])  # simple cache invalidator on row count
    signals, has_inventory, first_valid = _compute_signals(adj_key)
    standalone, is_sharpes = _standalone_backtests(adj_key)
    alpha, opt_weights, optimizer_by_cost, baseline_by_cost = _optimizer_backtests(adj_key)
    regime_masks = _build_regime_masks(adj_key)
    surviving = [n for n, s in is_sharpes.items() if s > 0]
    return DashboardState(
        prices=PriceData(adj_clean),
        adj_clean=adj_clean,
        futures=all_tradable_futures(),
        fut_adj=fut_adj,
        spy_returns=spy,
        signals=signals,
        is_sharpes=is_sharpes,
        surviving_signals=surviving,
        first_valid=first_valid,
        alpha_panel=alpha,
        opt_weights=opt_weights,
        optimizer_by_cost=optimizer_by_cost,
        baseline_by_cost=baseline_by_cost,
        standalone_by_signal=standalone,
        regime_masks=regime_masks,
        has_inventory=has_inventory,
    )


def evaluate_walkforward_cached(result: BacktestResult, spy: pd.Series) -> dict:
    """Thin wrapper; not @st.cache_data because BacktestResult isn't hashable."""
    return evaluate_walkforward(result, benchmark_returns=spy)


def evaluate_cached(result: BacktestResult, spy: pd.Series | None = None):
    return evaluate(result, benchmark_returns=spy)
