"""Universe definition for the project.

The universe is partitioned into three roles:

  - energy ETFs (Phase 1-4 universe; kept for the carry signal in Phase 5)
  - energy futures (Phase 5+ primary universe; yfinance front-month continuous)
  - benchmarks / regime indicators

ETF / futures pairings (`ETF_FUTURES_PAIRS`) drive the carry signal: for
each pair, the ETF-vs-futures return spread over a rolling window is the
realized roll yield. Negative spread = ETF underperformed = contango;
positive spread = backwardation.

Caveats on the futures series:
  - Yahoo's `=F` symbols return a front-month continuous series with
    UNDOCUMENTED roll methodology. Empirical inspection shows ~20-30 days
    with >10% moves over 16 years, of which roughly half are roll-induced
    discontinuities rather than genuine market events. This adds noise to
    momentum/reversal signals but does not bias them.
  - Yahoo does NOT preserve expired individual contracts (e.g. CLZ15.NYM
    returns 404), so a clean historical second-nearby continuous series
    cannot be built from this source for free. Carry is therefore computed
    via the ETF-spread proxy rather than from direct curve observation.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    category: str  # "etf" | "futures" | "benchmark" | "regime"


ENERGY_ETFS: tuple[Instrument, ...] = (
    Instrument("USO", "US Oil Fund (WTI ETF)", "etf"),
    Instrument("BNO", "US Brent Oil Fund (ETF)", "etf"),
    Instrument("UNG", "US Natural Gas Fund (ETF)", "etf"),
    Instrument("UGA", "US Gasoline Fund (ETF)", "etf"),
    Instrument("UHN", "US Heating Oil Fund (ETF, delisted 2018)", "etf"),
    Instrument("DBE", "Invesco DB Energy Fund (basket ETF)", "etf"),
)

ENERGY_FUTURES: tuple[Instrument, ...] = (
    Instrument("CL=F", "WTI Crude Oil (front-month continuous)", "futures"),
    Instrument("BZ=F", "Brent Crude Oil (front-month continuous)", "futures"),
    Instrument("NG=F", "Natural Gas (front-month continuous)", "futures"),
    Instrument("RB=F", "RBOB Gasoline (front-month continuous)", "futures"),
    Instrument("HO=F", "Heating Oil (front-month continuous)", "futures"),
)

BENCHMARKS: tuple[Instrument, ...] = (
    Instrument("SPY", "S&P 500 ETF", "benchmark"),
    Instrument("^VIX", "CBOE Volatility Index", "regime"),
)

UNIVERSE: tuple[Instrument, ...] = ENERGY_ETFS + ENERGY_FUTURES + BENCHMARKS


# ETF-to-futures pairings for the carry signal. UHN <-> HO=F not included
# because UHN delisted in 2018 (limited overlapping history).
ETF_FUTURES_PAIRS: dict[str, str] = {
    "USO": "CL=F",
    "BNO": "BZ=F",
    "UNG": "NG=F",
    "UGA": "RB=F",
}


def energy_tickers() -> list[str]:
    return [i.ticker for i in ENERGY_ETFS]


def energy_futures() -> list[str]:
    return [i.ticker for i in ENERGY_FUTURES]


def all_tickers() -> list[str]:
    return [i.ticker for i in UNIVERSE]
