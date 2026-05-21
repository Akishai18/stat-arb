"""CLI: refresh macro datasets (CFTC COT and, if EIA_API_KEY is set, EIA WPSR).

    uv run python -m statarb.cli.ingest_macro
    uv run python -m statarb.cli.ingest_macro --force --start-year 2010
"""

from __future__ import annotations

import argparse
import logging
import sys

from statarb.data.cftc import build_cot_panel
from statarb.data.eia import EIAKeyMissing, build_eia_panel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh CFTC and EIA datasets.")
    parser.add_argument("--start-year", type=int, default=2010)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--start", default="2009-01-01", help="EIA start ISO date")
    parser.add_argument("--force", action="store_true", help="Re-download cached annual files")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    print("--- CFTC COT ---")
    cot = build_cot_panel(start_year=args.start_year, end_year=args.end_year, force=args.force)
    print(
        f"COT panel: {len(cot)} rows, {cot['ticker'].nunique()} tickers, "
        f"{cot['as_of'].min().date()} -> {cot['as_of'].max().date()}"
    )

    print()
    print("--- EIA Weekly Petroleum Status ---")
    try:
        eia = build_eia_panel(start=args.start)
        print(
            f"EIA panel: {len(eia)} rows, {eia['ticker'].nunique()} tickers, "
            f"{eia['as_of'].min().date()} -> {eia['as_of'].max().date()}"
        )
    except EIAKeyMissing as e:
        print(f"SKIPPED: {e}")
        print("(CFTC COT is built and usable. Add EIA_API_KEY to enable inventory.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
