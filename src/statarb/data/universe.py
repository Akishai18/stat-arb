"""Universe definition for the project.

The universe is partitioned by role:

  - energy ETFs        Phase 1-4 universe; kept for the carry signal
  - energy futures     Phase 5-9 primary universe (5 contracts)
  - metals futures     Phase A1 expansion (5 contracts, COMEX + NYMEX)
  - grain futures      Phase A1 expansion (3 contracts, CBOT)
  - ETF carry pairs    one ETF per commodity for the realized-roll-yield carry signal
  - benchmarks         SPY + ^VIX for performance + regime classification

After Phase A1 the tradable universe is 13 commodities:
  5 energy (CL, BZ, NG, RB, HO) + 5 metals (GC, SI, HG, PL, PA) + 3 grains (ZC, ZW, ZS).

The carry signal needs an ETF pair per commodity. Where no clean
single-commodity ETF exists (some softs, livestock), the asset participates
in the universe via momentum/COT signals only -- carry contributes NaN for
those, and the Sharpe-weighted blend naturally down-weights NaN cells.

Caveats on the futures series:
  - Yahoo's `=F` symbols return a front-month continuous series with
    UNDOCUMENTED roll methodology. Empirical inspection of CL=F shows
    ~20-30 days with >10% moves over 16 years, of which roughly half
    are roll-induced discontinuities. Adds noise to momentum/reversal
    signals but does not bias them.
  - Yahoo does NOT preserve expired individual contracts, so a clean
    historical second-nearby continuous series cannot be built for free.
    Carry is computed via the ETF-vs-futures spread proxy.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    ticker: str
    name: str
    category: str  # "etf" | "futures" | "benchmark" | "regime"


# Energy ETFs (Phases 1-4 universe; still used for the carry signal's ETF leg)
ENERGY_ETFS: tuple[Instrument, ...] = (
    Instrument("USO", "US Oil Fund (WTI ETF)", "etf"),
    Instrument("BNO", "US Brent Oil Fund (ETF)", "etf"),
    Instrument("UNG", "US Natural Gas Fund (ETF)", "etf"),
    Instrument("UGA", "US Gasoline Fund (ETF)", "etf"),
    Instrument("UHN", "US Heating Oil Fund (ETF, delisted 2018)", "etf"),
    Instrument("DBE", "Invesco DB Energy Fund (basket ETF)", "etf"),
)

# Carry-pair ETFs added in Phase A1 (one per metal / grain commodity)
METAL_GRAIN_ETFS: tuple[Instrument, ...] = (
    Instrument("GLD", "SPDR Gold Trust", "etf"),
    Instrument("SLV", "iShares Silver Trust", "etf"),
    Instrument("CPER", "US Copper Index Fund", "etf"),
    Instrument("PPLT", "abrdn Physical Platinum Shares", "etf"),
    Instrument("PALL", "abrdn Physical Palladium Shares", "etf"),
    Instrument("CORN", "Teucrium Corn Fund", "etf"),
    Instrument("WEAT", "Teucrium Wheat Fund", "etf"),
    Instrument("SOYB", "Teucrium Soybean Fund", "etf"),
)

ENERGY_FUTURES: tuple[Instrument, ...] = (
    Instrument("CL=F", "WTI Crude Oil (front-month continuous)", "futures"),
    Instrument("BZ=F", "Brent Crude Oil (front-month continuous)", "futures"),
    Instrument("NG=F", "Natural Gas (front-month continuous)", "futures"),
    Instrument("RB=F", "RBOB Gasoline (front-month continuous)", "futures"),
    Instrument("HO=F", "Heating Oil (front-month continuous)", "futures"),
)

METALS_FUTURES: tuple[Instrument, ...] = (
    Instrument("GC=F", "Gold (COMEX front-month continuous)", "futures"),
    Instrument("SI=F", "Silver (COMEX front-month continuous)", "futures"),
    Instrument("HG=F", "Copper (COMEX front-month continuous)", "futures"),
    Instrument("PL=F", "Platinum (NYMEX front-month continuous)", "futures"),
    Instrument("PA=F", "Palladium (NYMEX front-month continuous)", "futures"),
)

GRAIN_FUTURES: tuple[Instrument, ...] = (
    Instrument("ZC=F", "Corn (CBOT front-month continuous)", "futures"),
    Instrument("ZW=F", "Wheat-SRW (CBOT front-month continuous)", "futures"),
    Instrument("ZS=F", "Soybeans (CBOT front-month continuous)", "futures"),
)

ALL_TRADABLE_FUTURES: tuple[Instrument, ...] = ENERGY_FUTURES + METALS_FUTURES + GRAIN_FUTURES

BENCHMARKS: tuple[Instrument, ...] = (
    Instrument("SPY", "S&P 500 ETF", "benchmark"),
    Instrument("^VIX", "CBOE Volatility Index", "regime"),
)

UNIVERSE: tuple[Instrument, ...] = (
    ENERGY_ETFS + METAL_GRAIN_ETFS + ALL_TRADABLE_FUTURES + BENCHMARKS
)


# ETF-to-futures pairings drive the carry signal: ETF underperformance
# vs the front-month futures proxies the realized roll yield. UHN <-> HO=F
# omitted because UHN delisted in 2018 (insufficient overlapping history).
ETF_FUTURES_PAIRS: dict[str, str] = {
    # Energy
    "USO": "CL=F",
    "BNO": "BZ=F",
    "UNG": "NG=F",
    "UGA": "RB=F",
    # Metals
    "GLD": "GC=F",
    "SLV": "SI=F",
    "CPER": "HG=F",
    "PPLT": "PL=F",
    "PALL": "PA=F",
    # Grains
    "CORN": "ZC=F",
    "WEAT": "ZW=F",
    "SOYB": "ZS=F",
}


def energy_tickers() -> list[str]:
    return [i.ticker for i in ENERGY_ETFS]


def metal_grain_etf_tickers() -> list[str]:
    return [i.ticker for i in METAL_GRAIN_ETFS]


def energy_futures() -> list[str]:
    return [i.ticker for i in ENERGY_FUTURES]


def metals_futures() -> list[str]:
    return [i.ticker for i in METALS_FUTURES]


def grain_futures() -> list[str]:
    return [i.ticker for i in GRAIN_FUTURES]


def all_tradable_futures() -> list[str]:
    """Full futures universe across energy + metals + grains (Phase A1+)."""
    return [i.ticker for i in ALL_TRADABLE_FUTURES]


def all_tickers() -> list[str]:
    return [i.ticker for i in UNIVERSE]
