"""yfinance loaders with parquet caching.

Public API:
    fetch_one(ticker, start, end, force) -> DataFrame
    build_universe(start, end, force)    -> (adj_close_panel, returns_panel)
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from statarb.data.paths import processed_path, raw_path
from statarb.data.universe import all_tickers

log = logging.getLogger(__name__)

DEFAULT_START = "2010-01-01"


def fetch_one(
    ticker: str,
    *,
    start: str = DEFAULT_START,
    end: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Fetch one ticker's daily OHLCV via yfinance, caching to parquet.

    Returns a DataFrame indexed by date with columns:
        open, high, low, close, adj_close, volume

    `adj_close` is yfinance's auto-adjusted close (split + dividend adjusted),
    suitable for return calculation.
    """
    path = raw_path(ticker)
    if path.exists() and not force:
        return pd.read_parquet(path)

    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        actions=False,
    )
    if df.empty:
        raise RuntimeError(f"yfinance returned empty data for {ticker!r}")

    # yfinance can return a MultiIndex on columns when given a list; flatten.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df.index.name = "date"
    df = df[["open", "high", "low", "close", "adj_close", "volume"]].sort_index()

    df.to_parquet(path)
    return df


def build_universe(
    *,
    start: str = DEFAULT_START,
    end: str | None = None,
    force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load every ticker in the universe, build adjusted-close + returns panels.

    Date index is the outer join of all tickers' trading days. Missing values
    are left as NaN deliberately -- forward-filling adjusted close would bias
    return calculations. Returns are computed with pct_change(), which yields
    NaN where the prior close is missing.
    """
    frames: dict[str, pd.Series] = {}
    failures: dict[str, Exception] = {}
    for ticker in all_tickers():
        try:
            df = fetch_one(ticker, start=start, end=end, force=force)
            frames[ticker] = df["adj_close"].rename(ticker)
            log.info("loaded %s: %d rows %s -> %s", ticker, len(df), df.index.min().date(), df.index.max().date())
        except Exception as exc:
            failures[ticker] = exc
            log.warning("failed to load %s: %s", ticker, exc)

    if not frames:
        raise RuntimeError(f"no tickers loaded. failures: {failures}")

    adj_close = pd.concat(frames.values(), axis=1).sort_index()
    adj_close.index.name = "date"
    returns = adj_close.pct_change()

    adj_close.to_parquet(processed_path("adj_close"))
    returns.to_parquet(processed_path("returns"))

    if failures:
        log.warning("partial universe load. failed tickers: %s", list(failures))

    return adj_close, returns


def universe_last_refreshed() -> date | None:
    """Most-recent date present in the processed adj_close panel, or None."""
    path = processed_path("adj_close")
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    return df.index.max().date()
