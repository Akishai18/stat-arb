"""LivePortfolio reconciliation: the incremental paper book must reproduce the
vectorized Backtester exactly.

If this fails, "paper trading" is measuring something other than the strategy
the research validated, and the live P&L is not comparable to the backtest CI.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.backtest import Backtester
from statarb.costs import LinearCostModel
from statarb.data import PriceData
from statarb.live.portfolio import LivePortfolio


def _make_prices(returns: pd.DataFrame, start_price: float = 100.0) -> PriceData:
    """Integrate a returns panel into prices, with a base row so the first
    return is recoverable via pct_change (mirrors the engine test helper)."""
    levels = (1.0 + returns.fillna(0.0)).cumprod() * start_price
    base = pd.DataFrame(
        [[start_price] * returns.shape[1]],
        columns=returns.columns,
        index=[returns.index[0] - pd.Timedelta(days=1)],
    )
    return PriceData(pd.concat([base, levels]))


def _random_weights(dates: pd.DatetimeIndex, assets: list[str], seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    raw = rng.uniform(-0.2, 0.2, size=(len(dates), len(assets)))
    w = pd.DataFrame(raw, index=dates, columns=assets)
    return w.sub(w.mean(axis=1), axis=0)  # demean -> dollar-neutral, like the real book


@pytest.fixture
def panel():
    dates = pd.bdate_range("2024-01-02", periods=40)
    assets = ["A", "B", "C", "D"]
    rng = np.random.default_rng(7)
    returns = pd.DataFrame(
        rng.normal(0.0, 0.01, size=(len(dates), len(assets))), index=dates, columns=assets
    )
    weights = _random_weights(dates, assets, seed=11)
    return dates, assets, returns, weights


def test_incremental_matches_backtester(panel, tmp_path):
    dates, _assets, returns, weights = panel
    prices = _make_prices(returns)
    cost_bps = 10

    bt_res = Backtester(prices, LinearCostModel(bps_per_side=cost_bps)).run(weights)

    port = LivePortfolio(initial_notional=100_000.0, cost_bps=cost_bps, base_dir=tmp_path)
    ret_panel = prices.returns()
    for d in dates:
        port.record_day(d, ret_panel.loc[d], weights.loc[d])

    live_net = port.ledger["net_return"]
    live_eq = port.ledger["equity"]

    np.testing.assert_allclose(live_net.to_numpy(), bt_res.net_returns.to_numpy(), atol=1e-12)
    np.testing.assert_allclose(live_eq.to_numpy(), bt_res.equity_curve.to_numpy(), atol=1e-12)
    np.testing.assert_allclose(
        port.ledger["turnover"].to_numpy(), bt_res.turnover.to_numpy(), atol=1e-12
    )


def test_starts_flat(panel, tmp_path):
    dates, _assets, returns, weights = panel
    prices = _make_prices(returns)
    port = LivePortfolio(base_dir=tmp_path)
    first = dates[0]
    rec = port.record_day(first, prices.returns().loc[first], weights.loc[first])
    # No book held on day one -> zero P&L, equity unchanged, notional intact.
    assert rec.net_return == 0.0
    assert rec.turnover == 0.0
    assert rec.equity == pytest.approx(1.0)
    assert rec.notional == pytest.approx(100_000.0)


def test_record_day_is_not_idempotent_guard(panel, tmp_path):
    dates, _assets, returns, weights = panel
    prices = _make_prices(returns)
    port = LivePortfolio(base_dir=tmp_path)
    d = dates[0]
    port.record_day(d, prices.returns().loc[d], weights.loc[d])
    with pytest.raises(ValueError, match="already recorded"):
        port.record_day(d, prices.returns().loc[d], weights.loc[d])


def test_persistence_round_trip(panel, tmp_path):
    dates, _assets, returns, weights = panel
    prices = _make_prices(returns)
    ret_panel = prices.returns()

    port = LivePortfolio(initial_notional=250_000.0, cost_bps=5, base_dir=tmp_path)
    for d in dates[:10]:
        port.record_day(d, ret_panel.loc[d], weights.loc[d])
    port.save()

    reloaded = LivePortfolio.load_or_create(base_dir=tmp_path)
    assert reloaded.initial_notional == 250_000.0
    assert reloaded.cost_bps == 5
    assert reloaded.last_processed_date() == dates[9]

    # Continuing on the reloaded book matches one built in a single pass.
    for d in dates[10:]:
        reloaded.record_day(d, ret_panel.loc[d], weights.loc[d])
    oneshot = LivePortfolio(initial_notional=250_000.0, cost_bps=5, base_dir=tmp_path / "b")
    for d in dates:
        oneshot.record_day(d, ret_panel.loc[d], weights.loc[d])
    np.testing.assert_allclose(
        reloaded.ledger["equity"].to_numpy(), oneshot.ledger["equity"].to_numpy(), atol=1e-12
    )
