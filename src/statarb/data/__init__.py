"""Data layer: loaders, point-in-time price access, on-disk caching.

Phase 1 added the ETF universe + benchmarks. Phase 5 added energy futures
(yfinance front-month continuous) and an ETF-to-futures pairing map used
by the carry signal.
"""

from statarb.data.cleaning import KNOWN_ANOMALIES, mask_known_anomalies
from statarb.data.loaders import build_universe, fetch_one, universe_last_refreshed
from statarb.data.panel import PriceData
from statarb.data.universe import (
    BENCHMARKS,
    ENERGY_ETFS,
    ENERGY_FUTURES,
    ETF_FUTURES_PAIRS,
    UNIVERSE,
    Instrument,
    all_tickers,
    energy_futures,
    energy_tickers,
)

__all__ = [
    "BENCHMARKS",
    "ENERGY_ETFS",
    "ENERGY_FUTURES",
    "ETF_FUTURES_PAIRS",
    "KNOWN_ANOMALIES",
    "UNIVERSE",
    "Instrument",
    "PriceData",
    "all_tickers",
    "build_universe",
    "energy_futures",
    "energy_tickers",
    "fetch_one",
    "mask_known_anomalies",
    "universe_last_refreshed",
]
