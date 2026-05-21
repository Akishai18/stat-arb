"""Backtesting engine.

THE SINGLE LAG RULE this engine enforces:
    A weight panel dated by the day its signal was computed is shifted by
    one day before being applied. The lag is centralized here so signal
    and portfolio-construction code stays lag-free and impossible to
    double-lag or zero-lag.
"""

from statarb.backtest.engine import Backtester
from statarb.backtest.result import BacktestResult

__all__ = ["BacktestResult", "Backtester"]
