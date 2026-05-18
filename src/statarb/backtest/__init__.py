"""Backtesting engine.

Convention enforced everywhere: a signal computed using data up to the close
of day t is tradable starting at day t+1. The engine is vectorized but
auditable - any backtest must pass the no-lookahead synthetic test in
tests/test_backtest_no_lookahead.py (added in Phase 2).
"""
