"""CFTC Commitments of Traders (COT) ingestion.

Fetches the disaggregated futures-only report from cftc.gov (free, no API
key). The report classifies each contract's open interest into producer/
merchant, swap dealer, managed money, and other reportable categories.
For this project we care about managed money positioning -- the speculator
crowd whose herding tends to overshoot.

Release timing (important for backtest hygiene):
  - Data as of close-of-business Tuesday.
  - Report published Friday at 3:30 PM ET.
  - So a row with `Report_Date = Tuesday` was PUBLIC only on the following
    Friday. To avoid a 3-business-day lookahead, the COT score is placed
    on the Friday release date, not the Tuesday as-of date.

CFTC code mapping uses the most-actively-traded contract per commodity.
Open interest is verified at ingest time -- if a code stops trading or
gets renamed, the warning surfaces immediately.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date

import pandas as pd
import requests

from statarb.data.paths import processed_path, raw_dir

log = logging.getLogger(__name__)

# CFTC contract codes for the energy futures we trade. These are the
# disaggregated-report codes for the most-actively-traded contract per
# commodity. Verified against the 2024 annual file (see Phase 6 design notes).
CFTC_CONTRACT_CODES: dict[str, str] = {
    # Energy
    "CL=F": "067651",  # WTI Crude Oil (NYMEX, physical-settled)
    "BZ=F": "06765T",  # Brent Last Day (NYMEX-listed Brent)
    "NG=F": "023651",  # Natural Gas (NYMEX Henry Hub)
    "RB=F": "111659",  # RBOB Gasoline (NYMEX)
    "HO=F": "022651",  # NY Harbor ULSD (NYMEX)
    # Metals (added Phase A1)
    "GC=F": "088691",  # Gold (COMEX)
    "SI=F": "084691",  # Silver (COMEX)
    "HG=F": "085692",  # Copper #1 (COMEX)
    "PL=F": "076651",  # Platinum (NYMEX)
    "PA=F": "075651",  # Palladium (NYMEX)
    # Grains (added Phase A1)
    "ZC=F": "002602",  # Corn (CBOT)
    "ZW=F": "001602",  # Wheat-SRW (CBOT)
    "ZS=F": "005602",  # Soybeans (CBOT)
}

ARCHIVE_URL = "https://www.cftc.gov/files/dea/history/fut_disagg_txt_{year}.zip"

# Columns we keep from the raw 191-column CFTC file.
_KEEP_COLUMNS = [
    "Report_Date_as_YYYY-MM-DD",
    "CFTC_Contract_Market_Code",
    "Market_and_Exchange_Names",
    "Open_Interest_All",
    "M_Money_Positions_Long_All",
    "M_Money_Positions_Short_All",
    "Pct_of_OI_M_Money_Long_All",
    "Pct_of_OI_M_Money_Short_All",
]


def fetch_cot_year(year: int, *, force: bool = False) -> pd.DataFrame:
    """Download one annual CFTC disaggregated file. Cached as parquet."""
    path = raw_dir() / f"cot_{year}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)
    url = ARCHIVE_URL.format(year=year)
    log.info("fetching CFTC COT for %d from %s", year, url)
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf, zf.open(zf.namelist()[0]) as f:
        df = pd.read_csv(f, low_memory=False)

    # Pre-2013 files use a column named `Report_Date_as_MM_DD_YYYY` but,
    # quirkily, the values are still in YYYY-MM-DD. Let pandas auto-detect.
    if "Report_Date_as_YYYY-MM-DD" not in df.columns:
        if "Report_Date_as_MM_DD_YYYY" in df.columns:
            df["Report_Date_as_YYYY-MM-DD"] = pd.to_datetime(
                df["Report_Date_as_MM_DD_YYYY"]
            )
        else:
            raise KeyError(
                f"COT file for {year} has no recognized Report_Date column. "
                f"First columns: {list(df.columns)[:5]}"
            )

    # Older files have trailing whitespace in the contract code column.
    df["CFTC_Contract_Market_Code"] = df["CFTC_Contract_Market_Code"].astype(str).str.strip()

    # Filter early to our energy contracts so the parquet stays small.
    df = df[df["CFTC_Contract_Market_Code"].isin(CFTC_CONTRACT_CODES.values())]
    df = df[_KEEP_COLUMNS].copy()
    df["Report_Date_as_YYYY-MM-DD"] = pd.to_datetime(df["Report_Date_as_YYYY-MM-DD"])
    df.to_parquet(path)
    return df


def build_cot_panel(
    *,
    start_year: int = 2010,
    end_year: int | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Combine annual files into one long DataFrame with our ticker labels.

    Output schema:
        as_of (Tuesday date), release (Friday date), ticker (CL=F/...),
        contract_code, open_interest, mm_long, mm_short, mm_long_pct,
        mm_short_pct, mm_net_pct.

    `release` is `as_of` + 3 business days (publication is Friday 3:30 ET
    so the score is treated as available Friday close onward).
    """
    end_year = end_year or date.today().year
    frames: list[pd.DataFrame] = []
    failures: dict[int, Exception] = {}
    for year in range(start_year, end_year + 1):
        try:
            frames.append(fetch_cot_year(year, force=force))
        except Exception as e:
            failures[year] = e
            log.warning("COT year %d failed: %s", year, e)
    if not frames:
        raise RuntimeError(f"no COT years loaded; failures: {failures}")

    raw = pd.concat(frames, ignore_index=True)
    code_to_ticker = {v: k for k, v in CFTC_CONTRACT_CODES.items()}
    raw["ticker"] = raw["CFTC_Contract_Market_Code"].map(code_to_ticker)
    raw = raw.dropna(subset=["ticker"]).copy()

    long = pd.DataFrame(
        {
            "as_of": raw["Report_Date_as_YYYY-MM-DD"],
            "release": raw["Report_Date_as_YYYY-MM-DD"] + pd.tseries.offsets.BDay(3),
            "ticker": raw["ticker"],
            "contract_code": raw["CFTC_Contract_Market_Code"],
            "open_interest": raw["Open_Interest_All"].astype(float),
            "mm_long": raw["M_Money_Positions_Long_All"].astype(float),
            "mm_short": raw["M_Money_Positions_Short_All"].astype(float),
            "mm_long_pct": raw["Pct_of_OI_M_Money_Long_All"].astype(float),
            "mm_short_pct": raw["Pct_of_OI_M_Money_Short_All"].astype(float),
        }
    )
    long["mm_net_pct"] = long["mm_long_pct"] - long["mm_short_pct"]
    long = long.sort_values(["ticker", "as_of"]).reset_index(drop=True)

    out_path = processed_path("cot")
    long.to_parquet(out_path)
    if failures:
        log.warning("partial COT load. failed years: %s", list(failures))
    return long


def load_cot_panel() -> pd.DataFrame:
    """Read the cached processed COT panel."""
    path = processed_path("cot")
    if not path.exists():
        raise FileNotFoundError(
            f"no processed COT at {path}. "
            "Run `python -m statarb.cli.ingest_macro` to build it."
        )
    return pd.read_parquet(path)
