"""CLI: refresh the data universe.

    uv run python -m statarb.cli.ingest
    uv run python -m statarb.cli.ingest --force --start 2015-01-01
"""

from __future__ import annotations

import argparse
import logging
import sys

from statarb.data.loaders import DEFAULT_START, build_universe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the statarb data universe.")
    parser.add_argument("--start", default=DEFAULT_START, help="ISO start date")
    parser.add_argument("--end", default=None, help="ISO end date (default: today)")
    parser.add_argument("--force", action="store_true", help="Re-download cached tickers")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    adj_close, returns = build_universe(start=args.start, end=args.end, force=args.force)
    print(
        f"loaded {adj_close.shape[1]} tickers, "
        f"{adj_close.shape[0]} dates from {adj_close.index.min().date()} "
        f"to {adj_close.index.max().date()}"
    )
    print(f"adj_close panel: {adj_close.shape}, returns panel: {returns.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
