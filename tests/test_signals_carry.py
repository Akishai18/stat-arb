"""Carry signal: hand-traced spreads, NaN propagation, validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.signals import realized_carry


def _panel(**columns: list[float]) -> pd.DataFrame:
    n = len(next(iter(columns.values())))
    return pd.DataFrame(
        columns,
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
    )


def test_carry_hand_traced_pair():
    """ETF goes 100 -> 110 (10%); futures goes 100 -> 120 (20%).
    Carry = 0.10 - 0.20 = -0.10 (ETF underperformed -> contango).
    """
    panel = _panel(
        USO=[100.0, 100.0, 110.0],
        **{"CL=F": [100.0, 100.0, 120.0]},
    )
    carry = realized_carry(panel, pairs={"USO": "CL=F"}, lookback=2)
    assert carry["CL=F"].iloc[2] == pytest.approx(-0.10)


def test_carry_indexed_by_futures_ticker():
    panel = _panel(
        USO=[100.0, 110.0],
        BNO=[100.0, 105.0],
        **{"CL=F": [100.0, 120.0]},
        **{"BZ=F": [100.0, 115.0]},
    )
    carry = realized_carry(
        panel,
        pairs={"USO": "CL=F", "BNO": "BZ=F"},
        lookback=1,
    )
    # Output columns are the futures tickers, not ETF tickers
    assert list(carry.columns) == ["CL=F", "BZ=F"]
    # USO underperformed: 0.10 - 0.20 = -0.10
    assert carry["CL=F"].iloc[1] == pytest.approx(-0.10)
    # BNO underperformed: 0.05 - 0.15 = -0.10
    assert carry["BZ=F"].iloc[1] == pytest.approx(-0.10)


def test_carry_backwardation_produces_positive_score():
    """If ETF beats futures (backwardation regime), carry should be positive."""
    panel = _panel(
        USO=[100.0, 120.0],
        **{"CL=F": [100.0, 110.0]},
    )
    carry = realized_carry(panel, pairs={"USO": "CL=F"}, lookback=1)
    assert carry["CL=F"].iloc[1] == pytest.approx(0.20 - 0.10)


def test_carry_first_rows_are_nan():
    panel = _panel(
        USO=[100.0, 105.0, 110.0],
        **{"CL=F": [100.0, 105.0, 110.0]},
    )
    carry = realized_carry(panel, pairs={"USO": "CL=F"}, lookback=2)
    assert pd.isna(carry["CL=F"].iloc[0])
    assert pd.isna(carry["CL=F"].iloc[1])


def test_carry_handles_nan_in_etf_or_futures():
    panel = _panel(
        USO=[100.0, np.nan, 110.0],
        **{"CL=F": [100.0, 105.0, 120.0]},
    )
    carry = realized_carry(panel, pairs={"USO": "CL=F"}, lookback=2)
    # Row 2 needs USO at index 0 (100) and 2 (110): both OK -> ETF ret 0.10
    # Futures: 100 -> 120: 0.20. Carry = -0.10
    assert carry["CL=F"].iloc[2] == pytest.approx(-0.10)


def test_carry_rejects_bad_lookback():
    panel = _panel(USO=[1.0, 2.0], **{"CL=F": [1.0, 2.0]})
    with pytest.raises(ValueError):
        realized_carry(panel, pairs={"USO": "CL=F"}, lookback=0)


def test_carry_rejects_empty_pairs():
    panel = _panel(USO=[1.0, 2.0])
    with pytest.raises(ValueError):
        realized_carry(panel, pairs={})


def test_carry_rejects_missing_ticker():
    panel = _panel(USO=[1.0, 2.0])  # CL=F not in panel
    with pytest.raises(ValueError, match="missing"):
        realized_carry(panel, pairs={"USO": "CL=F"})


def test_carry_signal_is_point_in_time_safe():
    """Truncating the future should not change carry scores computed earlier."""
    rng = np.random.default_rng(0)
    n = 40
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    etf_path = np.cumprod(1 + rng.normal(0, 0.01, n)) * 100
    fut_path = np.cumprod(1 + rng.normal(0, 0.01, n)) * 100
    panel = pd.DataFrame({"USO": etf_path, "CL=F": fut_path}, index=idx)
    full = realized_carry(panel, pairs={"USO": "CL=F"}, lookback=5)
    cutoff = idx[25]
    trunc = realized_carry(panel.loc[:cutoff], pairs={"USO": "CL=F"}, lookback=5)
    pd.testing.assert_frame_equal(full.loc[:cutoff].dropna(), trunc.loc[:cutoff].dropna())
