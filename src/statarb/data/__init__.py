"""Data layer: loaders, point-in-time price access, on-disk caching.

Phase 1 added the ETF universe + benchmarks. Phase 5 added energy futures
(yfinance front-month continuous) and an ETF-to-futures pairing map used
by the carry signal.
"""

from statarb.data.cleaning import KNOWN_ANOMALIES, mask_known_anomalies
from statarb.data.loaders import build_universe, fetch_one, universe_last_refreshed
from statarb.data.panel import PriceData
from statarb.data.universe import (
    ALL_TRADABLE_FUTURES,
    BENCHMARKS,
    ENERGY_ETFS,
    ENERGY_FUTURES,
    ETF_FUTURES_PAIRS,
    GRAIN_FUTURES,
    METAL_GRAIN_ETFS,
    METALS_FUTURES,
    UNIVERSE,
    Instrument,
    all_tickers,
    all_tradable_futures,
    energy_futures,
    energy_tickers,
    grain_futures,
    metal_grain_etf_tickers,
    metals_futures,
)

__all__ = [
    "ALL_TRADABLE_FUTURES",
    "BENCHMARKS",
    "ENERGY_ETFS",
    "ENERGY_FUTURES",
    "ETF_FUTURES_PAIRS",
    "GRAIN_FUTURES",
    "KNOWN_ANOMALIES",
    "METALS_FUTURES",
    "METAL_GRAIN_ETFS",
    "UNIVERSE",
    "Instrument",
    "PriceData",
    "all_tickers",
    "all_tradable_futures",
    "build_universe",
    "energy_futures",
    "energy_tickers",
    "fetch_one",
    "grain_futures",
    "mask_known_anomalies",
    "metal_grain_etf_tickers",
    "metals_futures",
    "universe_last_refreshed",
]
