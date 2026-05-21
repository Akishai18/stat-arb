"""Universe constants are well-formed and non-empty."""

from statarb.data import (
    BENCHMARKS,
    ENERGY_ETFS,
    ENERGY_FUTURES,
    ETF_FUTURES_PAIRS,
    UNIVERSE,
    all_tickers,
    energy_futures,
    energy_tickers,
)


def test_energy_tickers_present():
    tickers = set(energy_tickers())
    assert {"USO", "BNO", "UNG", "UGA", "UHN", "DBE"} <= tickers


def test_benchmarks_present():
    tickers = {i.ticker for i in BENCHMARKS}
    assert {"SPY", "^VIX"} <= tickers


def test_universe_is_union():
    assert set(all_tickers()) == {i.ticker for i in UNIVERSE}
    assert len(UNIVERSE) == len(ENERGY_ETFS) + len(ENERGY_FUTURES) + len(BENCHMARKS)


def test_energy_futures_present():
    tickers = set(energy_futures())
    assert {"CL=F", "BZ=F", "NG=F", "RB=F", "HO=F"} <= tickers


def test_etf_futures_pairs_consistency():
    """Every key of ETF_FUTURES_PAIRS must be an ETF; every value a futures ticker."""
    etf_set = {i.ticker for i in ENERGY_ETFS}
    fut_set = {i.ticker for i in ENERGY_FUTURES}
    for etf, fut in ETF_FUTURES_PAIRS.items():
        assert etf in etf_set, f"{etf} in pairs but not an ETF"
        assert fut in fut_set, f"{fut} in pairs but not a futures ticker"


def test_no_duplicate_tickers():
    tickers = all_tickers()
    assert len(tickers) == len(set(tickers))
