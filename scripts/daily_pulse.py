"""Daily live pulse: advance the paper book to the latest available close.

This is the scheduled job that turns the locked headline strategy into an
out-of-sample paper trace. Each run:

    1. (optionally) refreshes prices + COT so the latest close is available;
    2. rebuilds the headline target panel via the shared `live.pipeline`
       (the SAME code the dashboard trades -- no second copy to drift);
    3. refuses to proceed if the latest close is stale (likely a broken
       ingest) so the trace is never corrupted with old data;
    4. records EVERY trading day the book has not yet seen, in order -- not
       just the latest -- so a missed run (laptop asleep, skipped cron) is
       caught up on the next pulse rather than leaving a permanent hole;
    5. persists state to `<data_root>/live/` and appends one human-readable
       line per recorded day to `live/log.txt`.

Idempotent and gap-resilient: re-running on the same data is a no-op (the book
refuses to double-record a date), and missing N runs just means the next run
records N days. The book starts flat on the very first pulse -- a genuine OOS
trace with no back-seeded history (only the latest day is taken, not all of
history).

Schedule on macOS via launchd (preferred over cron on a laptop that sleeps --
a missed fire is caught up on the next run): see `scripts/launchd/` and load
with `launchctl load ~/Library/LaunchAgents/com.statarb.dailypulse.plist`.

Usage:
    uv run python scripts/daily_pulse.py              # refresh data, then pulse
    uv run python scripts/daily_pulse.py --no-refresh # pulse on existing data
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

import pandas as pd

from statarb.cli import ingest, ingest_macro
from statarb.data import PriceData, mask_known_anomalies
from statarb.data.cftc import load_cot_panel
from statarb.data.paths import data_root
from statarb.live.pipeline import COST_BPS, headline_target_weights, latest_target
from statarb.live.portfolio import DEFAULT_NOTIONAL, LivePortfolio

log = logging.getLogger("daily_pulse")

# A market close older than this (calendar days) relative to the run date means
# ingest is likely broken. 5 covers a Friday close seen the following Wednesday
# across a Monday holiday; anything beyond that is a red flag, not a long weekend.
MAX_STALENESS_DAYS = 5


def _refresh_data() -> None:
    """Pull the latest prices and COT. Force=True so the most recent bars are
    re-downloaded rather than served from yesterday's cache."""
    log.info("refreshing price universe...")
    ingest.main(["--force"])
    log.info("refreshing macro (COT/EIA)...")
    ingest_macro.main(["--force"])


def _format(rec) -> str:
    return (
        f"{datetime.now(UTC).isoformat()}  recorded {rec.date.date()}  "
        f"net={rec.net_return:+.4%}  equity={rec.equity:.4f}  "
        f"notional={rec.notional:,.2f}  turnover={rec.turnover:.3f}  "
        f"gross_exp={rec.gross_exposure:.2f}  net_exp={rec.net_exposure:+.3f}  "
        f"L/S={rec.n_long}/{rec.n_short}"
    )


def run_pulse(
    *,
    notional: float,
    cost_bps: float,
    refresh: bool,
    max_staleness_days: int = MAX_STALENESS_DAYS,
) -> int:
    if refresh:
        _refresh_data()

    adj_clean = mask_known_anomalies(PriceData.load().adj_close())
    prices = PriceData(adj_clean)
    cot_panel = load_cot_panel()
    returns = prices.returns()

    weights = headline_target_weights(adj_clean, cot_panel)
    latest_date = pd.Timestamp(latest_target(weights).name)

    # Freshness guard: never record on stale data -- that would corrupt the
    # trace. A non-zero exit lets a watcher notice the book stopped advancing.
    staleness = (pd.Timestamp.now().normalize() - latest_date).days
    if staleness > max_staleness_days:
        log.warning(
            "STALE DATA: latest close %s is %d calendar days old (> %d) -- "
            "skipping pulse; check ingest.",
            latest_date.date(),
            staleness,
            max_staleness_days,
        )
        return 1

    port = LivePortfolio.load_or_create(initial_notional=notional, cost_bps=cost_bps)
    last = port.last_processed_date()

    # Which trading days to record. On the first-ever pulse the book starts
    # flat (take only the latest day -- no back-seeded history). Otherwise catch
    # up every trading day the book has not seen, in order, so missed runs heal.
    if last is None:
        to_record = [latest_date]
    else:
        to_record = [d for d in weights.index if last < d <= latest_date]

    if not to_record:
        log.info(
            "no new trading day to record (book at %s, latest close %s) -- no-op",
            last.date() if last is not None else None,
            latest_date.date(),
        )
        return 0

    if last is not None and len(to_record) > 1:
        log.warning(
            "catching up %d missed trading days (%s .. %s)",
            len(to_record),
            to_record[0].date(),
            to_record[-1].date(),
        )

    recs = [port.record_day(d, returns.loc[d], weights.loc[d]) for d in to_record]
    port.save()

    log_path = data_root() / "live" / "log.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as fh:
        for rec in recs:
            line = _format(rec)
            fh.write(line + "\n")
            log.info(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advance the live paper book by one day.")
    parser.add_argument(
        "--notional", type=float, default=DEFAULT_NOTIONAL, help="initial paper notional (USD)"
    )
    parser.add_argument(
        "--cost-bps", type=float, default=COST_BPS, help="round-trip-per-side cost in bps"
    )
    parser.add_argument(
        "--no-refresh", action="store_true", help="skip data download; pulse on existing data"
    )
    parser.add_argument(
        "--max-staleness-days",
        type=int,
        default=MAX_STALENESS_DAYS,
        help="skip the pulse if the latest close is older than this many days",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    return run_pulse(
        notional=args.notional,
        cost_bps=args.cost_bps,
        refresh=not args.no_refresh,
        max_staleness_days=args.max_staleness_days,
    )


if __name__ == "__main__":
    sys.exit(main())
