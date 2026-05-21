"""Signal combination: z-scoring + linear weighting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from statarb.signals import combine, cross_sectional_zscore, sharpe_weighted_combine


def _panel(values: list[list[float]]) -> pd.DataFrame:
    n = len(values)
    return pd.DataFrame(
        values,
        index=pd.date_range("2020-01-01", periods=n, freq="B"),
        columns=list("ABCD"),
    )


def test_combine_single_signal_equals_its_zscore():
    a = _panel([[1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0]])
    combined = combine({"momentum": a})
    pd.testing.assert_frame_equal(combined, cross_sectional_zscore(a))


def test_combine_two_equal_weight_signals():
    """Equal weight = half each z-score, summed."""
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    b = _panel([[4.0, 3.0, 2.0, 1.0]])
    combined = combine({"a": a, "b": b})
    expected = 0.5 * cross_sectional_zscore(a) + 0.5 * cross_sectional_zscore(b)
    pd.testing.assert_frame_equal(combined, expected)


def test_combine_opposite_signals_cancel():
    """If signals a and b = -a are equal-weighted, they should cancel to zero."""
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    combined = combine({"a": a, "anti_a": -a})
    np.testing.assert_allclose(combined.values, 0.0, atol=1e-12)


def test_combine_custom_weights_are_normalized():
    """Weights of (2, 1) behave the same as (4, 2) -- both produce 2/3, 1/3 split."""
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    b = _panel([[4.0, 3.0, 2.0, 1.0]])
    combined1 = combine({"a": a, "b": b}, weights={"a": 2.0, "b": 1.0})
    combined2 = combine({"a": a, "b": b}, weights={"a": 4.0, "b": 2.0})
    pd.testing.assert_frame_equal(combined1, combined2)


def test_combine_rejects_misaligned_index():
    a = pd.DataFrame(
        [[1.0, 2.0]], index=pd.date_range("2020-01-01", periods=1, freq="B"), columns=["A", "B"]
    )
    b = pd.DataFrame(
        [[1.0, 2.0]], index=pd.date_range("2020-02-01", periods=1, freq="B"), columns=["A", "B"]
    )
    with pytest.raises(ValueError, match="index"):
        combine({"a": a, "b": b})


def test_combine_rejects_misaligned_columns():
    a = pd.DataFrame(
        [[1.0, 2.0]], index=pd.date_range("2020-01-01", periods=1, freq="B"), columns=["A", "B"]
    )
    b = pd.DataFrame(
        [[1.0, 2.0]], index=pd.date_range("2020-01-01", periods=1, freq="B"), columns=["A", "C"]
    )
    with pytest.raises(ValueError, match="columns"):
        combine({"a": a, "b": b})


def test_combine_rejects_missing_weight():
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    with pytest.raises(ValueError, match="missing"):
        combine({"a": a, "b": a}, weights={"a": 1.0})


def test_combine_rejects_all_zero_weights():
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    with pytest.raises(ValueError, match="zero"):
        combine({"a": a, "b": a}, weights={"a": 0.0, "b": 0.0})


def test_combine_rejects_empty_input():
    with pytest.raises(ValueError):
        combine({})


# ---------------------------------------------------------------------------
# Sharpe-weighted combine
# ---------------------------------------------------------------------------


def test_sharpe_weighted_drops_negative_sharpe_signals():
    """A signal with negative IS Sharpe should get weight 0; output should
    equal a single-signal combine over the survivors."""
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    b = _panel([[4.0, 3.0, 2.0, 1.0]])
    c = _panel([[1.0, 1.0, 1.0, 1.0]])  # zero variance
    out = sharpe_weighted_combine(
        {"a": a, "b": b, "c": c},
        is_sharpes={"a": 0.5, "b": -0.2, "c": 0.1},
    )
    # Expected: 'a' and 'c' contribute (positive Sharpes), 'b' is dropped.
    # 'c' has zero variance so cross_sectional_zscore -> all NaN.
    expected = combine({"a": a, "c": c}, weights={"a": 0.5, "c": 0.1})
    pd.testing.assert_frame_equal(out, expected)


def test_sharpe_weighted_proportional_to_positive_sharpes():
    """Sharpe weights are proportional, so weights of (0.5, 0.5) == (2.0, 2.0)."""
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    b = _panel([[4.0, 3.0, 2.0, 1.0]])
    out_low = sharpe_weighted_combine({"a": a, "b": b}, is_sharpes={"a": 0.5, "b": 0.5})
    out_high = sharpe_weighted_combine({"a": a, "b": b}, is_sharpes={"a": 2.0, "b": 2.0})
    pd.testing.assert_frame_equal(out_low, out_high)


def test_sharpe_weighted_falls_back_to_equal_weight_if_all_negative():
    """If every signal has Sharpe <= 0, fall back to equal weight rather than
    return all zeros."""
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    b = _panel([[4.0, 3.0, 2.0, 1.0]])
    out = sharpe_weighted_combine({"a": a, "b": b}, is_sharpes={"a": -0.1, "b": -0.5})
    expected = combine({"a": a, "b": b})  # equal-weight default
    pd.testing.assert_frame_equal(out, expected)


def test_sharpe_weighted_floor_at_zero_false_allows_sign_flip():
    """With floor_at_zero=False, negative Sharpe inverts the signal."""
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    out_flipped = sharpe_weighted_combine(
        {"a": a}, is_sharpes={"a": -1.0}, floor_at_zero=False,
    )
    out_normal = sharpe_weighted_combine(
        {"a": a}, is_sharpes={"a": 1.0}, floor_at_zero=False,
    )
    # Inverting Sharpe should invert the resulting combined score.
    np.testing.assert_allclose(out_flipped.to_numpy(), -out_normal.to_numpy(), atol=1e-12)


def test_sharpe_weighted_rejects_missing_sharpes():
    a = _panel([[1.0, 2.0, 3.0, 4.0]])
    b = _panel([[4.0, 3.0, 2.0, 1.0]])
    with pytest.raises(ValueError, match="missing"):
        sharpe_weighted_combine({"a": a, "b": b}, is_sharpes={"a": 0.5})
