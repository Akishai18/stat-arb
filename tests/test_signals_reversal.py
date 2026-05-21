"""Reversal signal: hand-traced values and parameter validation."""

from __future__ import annotations

import pandas as pd
import pytest

from statarb.signals import momentum, reversal


def _prices(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"A": values},
        index=pd.date_range("2020-01-01", periods=len(values), freq="B"),
    )


def test_reversal_hand_calculation():
    """Sign-flipped trailing return. price 100 -> 110 means a positive trailing
    return of +10%, so reversal score = -0.10."""
    p = _prices([100, 105, 110, 95])
    r = reversal(p, lookback=2)
    # row 2: -(110/100 - 1) = -0.10
    assert r["A"].iloc[2] == pytest.approx(-0.10)
    # row 3: -(95/105 - 1) ~ +0.09524 (loss -> positive reversal score)
    assert r["A"].iloc[3] == pytest.approx(-(95 / 105 - 1))


def test_reversal_early_rows_are_nan():
    p = _prices([100, 105, 110])
    r = reversal(p, lookback=2)
    assert pd.isna(r["A"].iloc[0])
    assert pd.isna(r["A"].iloc[1])


def test_reversal_equals_negated_momentum_with_skip_zero():
    """reversal(prices, lookback=N) is by construction -momentum(prices, lookback=N, skip=0)."""
    p = _prices([100, 102, 99, 105, 108, 110])
    rev = reversal(p, lookback=3)
    mom = momentum(p, lookback=3, skip=0)
    pd.testing.assert_frame_equal(rev, -mom)


def test_reversal_rejects_bad_lookback():
    p = _prices([100, 105])
    with pytest.raises(ValueError):
        reversal(p, lookback=0)
    with pytest.raises(ValueError):
        reversal(p, lookback=-1)
