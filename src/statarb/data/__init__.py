"""Data layer: loaders, cleaners, and point-in-time price access.

Phase 1 target: pull daily OHLCV for energy ETFs (USO, BNO, UNG, UGA, UHN, DBE)
plus benchmarks (SPY, ^VIX) via yfinance, cache as parquet, and expose an
as-of API that refuses to leak future data.
"""
