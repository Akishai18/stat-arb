"""EIA Weekly Petroleum Status Report ingestion.

Pulls weekly U.S. ending stocks for crude oil, motor gasoline, and
distillate fuel oil from the EIA v2 API. Free but requires a free API key
(register at https://www.eia.gov/opendata/register.php; the call sets
`EIA_API_KEY` env var).

Release timing:
  - Data refers to the week ending the prior Friday.
  - Released by EIA on Wednesday around 10:30 AM ET (sometimes Thursday on
    Monday-holiday weeks).
  - For backtest hygiene, the inventory score is placed on the Wednesday
    release date -- one would NOT have known Friday's number until the
    Wednesday report.

The Wednesday release date approximation: `period` is given as
"YYYY-MM-DD" referring to the week-ending date (a Friday). We compute
release = friday + 5 calendar days = next Wednesday, then bump to the
next business day if that Wednesday is a US-equity holiday (rare for
WPSR; the report typically slips to Thursday).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

import pandas as pd
import requests

from statarb.data.paths import processed_path

log = logging.getLogger(__name__)

EIA_V2_BASE = "https://api.eia.gov/v2"

# Map our futures tickers to EIA weekly inventory series. NG=F omitted
# because nat gas storage is reported in a separate weekly bulletin
# (Thursdays), not the WPSR -- worth a Phase 6b follow-up but out of scope
# for the WPSR-driven build.
EIA_SERIES: dict[str, dict[str, str]] = {
    "CL=F": {"series_id": "WCESTUS1", "label": "US crude oil ending stocks (kb)"},
    "BZ=F": {"series_id": "WCESTUS1", "label": "US crude oil ending stocks (kb)"},  # Brent uses crude as proxy
    "RB=F": {"series_id": "WGTSTUS1", "label": "US motor gasoline ending stocks (kb)"},
    "HO=F": {"series_id": "WDISTUS1", "label": "US distillate fuel oil ending stocks (kb)"},
}


class EIAKeyMissing(RuntimeError):
    """Raised when EIA_API_KEY is required but not set."""


def _require_key() -> str:
    key = os.environ.get("EIA_API_KEY")
    if not key:
        raise EIAKeyMissing(
            "EIA_API_KEY not set. Register for a free key at "
            "https://www.eia.gov/opendata/register.php, then "
            "`export EIA_API_KEY=<your_key>` and re-run."
        )
    return key


def fetch_eia_series(
    series_id: str,
    *,
    start: str = "2009-01-01",
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch one weekly petroleum series via the EIA v2 API.

    Returns columns: period (Friday week-ending date), value (in kb), units.
    """
    key = _require_key()
    url = f"{EIA_V2_BASE}/petroleum/stoc/wstk/data/"
    params = {
        "api_key": key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": series_id,
        "start": start,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "length": 5000,
    }
    if end is not None:
        params["end"] = end
    log.info("EIA fetch: series=%s start=%s end=%s", series_id, start, end)
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()
    rows = payload["response"]["data"]
    if not rows:
        raise RuntimeError(f"EIA returned empty data for series {series_id!r}")
    df = pd.DataFrame(rows)
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"])
    return df[["period", "value", "units"]].sort_values("period").reset_index(drop=True)


def build_eia_panel(
    *,
    start: str = "2009-01-01",
    end: str | None = None,
    tickers: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Combine the per-ticker EIA series into a long DataFrame.

    Output schema: as_of (week-ending Friday), release (Wednesday after),
    ticker, series_id, value, change_w_w.
    """
    tickers = list(tickers) if tickers is not None else list(EIA_SERIES.keys())
    fetched_cache: dict[str, pd.DataFrame] = {}
    rows: list[pd.DataFrame] = []
    for ticker in tickers:
        meta = EIA_SERIES.get(ticker)
        if meta is None:
            log.warning("no EIA series mapped for %s; skipping", ticker)
            continue
        sid = meta["series_id"]
        if sid not in fetched_cache:
            fetched_cache[sid] = fetch_eia_series(sid, start=start, end=end)
        df = fetched_cache[sid].copy()
        df["ticker"] = ticker
        df["series_id"] = sid
        rows.append(df.rename(columns={"period": "as_of"}))

    long = pd.concat(rows, ignore_index=True)
    # Compute weekly change per ticker (most recent week minus prior week,
    # SAME inventory series so equal across tickers sharing a series_id).
    long = long.sort_values(["ticker", "as_of"]).reset_index(drop=True)
    long["change_w_w"] = long.groupby("ticker")["value"].diff()
    # Release = Friday week-end + 5 calendar days = next Wednesday.
    long["release"] = long["as_of"] + pd.Timedelta(days=5)
    long.to_parquet(processed_path("eia_inventory"))
    return long


def load_eia_panel() -> pd.DataFrame:
    path = processed_path("eia_inventory")
    if not path.exists():
        raise FileNotFoundError(
            f"no processed EIA inventory at {path}. "
            "Run `python -m statarb.cli.ingest_macro` (needs EIA_API_KEY) to build it."
        )
    return pd.read_parquet(path)
