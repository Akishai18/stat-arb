"""Smoke tests: the package and all subpackages import cleanly."""

import statarb
from statarb import backtest, costs, data, evaluation, portfolio, signals


def test_version():
    assert statarb.__version__


def test_subpackages_importable():
    for mod in (data, signals, backtest, portfolio, costs, evaluation):
        assert mod.__doc__
