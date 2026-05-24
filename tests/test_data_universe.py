"""Universe constants are well-formed and non-empty."""

from statarb.data import (
    BENCHMARKS,
    ENERGY_ETFS,
    ENERGY_FUTURES,
    ETF_FUTURES_PAIRS,
    GRAIN_FUTURES,
    METAL_GRAIN_ETFS,
    METALS_FUTURES,
    UNIVERSE,
    all_tickers,
    all_tradable_futures,
    energy_futures,
    energy_tickers,
    grain_futures,
    metal_grain_etf_tickers,
    metals_futures,
)


def test_energy_tickers_present():
    tickers = set(energy_tickers())
    assert {"USO", "BNO", "UNG", "UGA", "UHN", "DBE"} <= tickers


def test_benchmarks_present():
    tickers = {i.ticker for i in BENCHMARKS}
    assert {"SPY", "^VIX"} <= tickers


def test_universe_is_union():
    assert set(all_tickers()) == {i.ticker for i in UNIVERSE}
    assert len(UNIVERSE) == (
        len(ENERGY_ETFS)
        + len(METAL_GRAIN_ETFS)
        + len(ENERGY_FUTURES)
        + len(METALS_FUTURES)
        + len(GRAIN_FUTURES)
        + len(BENCHMARKS)
    )


def test_energy_futures_present():
    tickers = set(energy_futures())
    assert {"CL=F", "BZ=F", "NG=F", "RB=F", "HO=F"} <= tickers


def test_metals_futures_present():
    tickers = set(metals_futures())
    assert {"GC=F", "SI=F", "HG=F", "PL=F", "PA=F"} <= tickers


def test_grain_futures_present():
    tickers = set(grain_futures())
    assert {"ZC=F", "ZW=F", "ZS=F"} <= tickers


def test_all_tradable_futures_is_union():
    tickers = set(all_tradable_futures())
    assert tickers == set(energy_futures()) | set(metals_futures()) | set(grain_futures())
    # 5 energy + 5 metals + 3 grains = 13
    assert len(tickers) == 13


def test_metal_grain_etfs_present():
    tickers = set(metal_grain_etf_tickers())
    assert {"GLD", "SLV", "CPER", "PPLT", "PALL", "CORN", "WEAT", "SOYB"} <= tickers


def test_etf_futures_pairs_consistency():
    """Every key of ETF_FUTURES_PAIRS must be an ETF in our universe;
    every value must be a tradable futures ticker."""
    etf_set = {i.ticker for i in ENERGY_ETFS} | {i.ticker for i in METAL_GRAIN_ETFS}
    fut_set = set(all_tradable_futures())
    for etf, fut in ETF_FUTURES_PAIRS.items():
        assert etf in etf_set, f"{etf} in pairs but not an ETF"
        assert fut in fut_set, f"{fut} in pairs but not a tradable futures ticker"


def test_etf_pairs_cover_all_tradable_futures_except_ho():
    """Every tradable futures contract should have an ETF pair for carry,
    except HO=F (UHN delisted 2018, no current ETF pair)."""
    paired_futures = set(ETF_FUTURES_PAIRS.values())
    unpaired = set(all_tradable_futures()) - paired_futures
    assert unpaired == {"HO=F"}, f"expected only HO=F unpaired, got {unpaired}"


def test_no_duplicate_tickers():
    tickers = all_tickers()
    assert len(tickers) == len(set(tickers))
