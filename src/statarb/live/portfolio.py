"""LivePortfolio: an incremental, parquet-persisted paper book.

The vectorized `Backtester` computes the whole P&L history at once. A live book
must instead accumulate one trading day at a time as real data arrives -- but it
must produce *identical* numbers, or "paper trading" measures something other
than the strategy we validated. This class is therefore a faithful incremental
re-statement of the engine's locked contract:

    net[t]      = W[t-1] . r[t]  -  cost(|W[t-1] - W[t-2]|)
    equity[t]   = equity[t-1] * (1 + net[t])      equity[-1] = 1.0
    turnover[t] = sum_i |W[t-1,i] - W[t-2,i]|       (two-sided)
    cost[t]     = (bps_per_side / 1e4) * turnover[t]

where W[t] is the target set at the close of day t (held the following day) and
r[t] is the simple close-to-close return on day t. On the first pulse the book
holds nothing, so it starts flat -- a genuine out-of-sample trace with no
back-seeded history. `tests/test_live_portfolio.py` asserts the day-by-day
equity equals `Backtester.run(weights)` on the same target panel.

State persists to `<data_root>/live/`:
    targets.parquet   date x asset target weights (one row appended per pulse)
    ledger.parquet    date-indexed daily P&L records
    meta.json         initial notional, cost bps, timestamps
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from statarb.data.paths import data_root
from statarb.live.pipeline import COST_BPS

DEFAULT_NOTIONAL = 100_000.0

LEDGER_COLUMNS = [
    "gross_return",
    "turnover",
    "cost",
    "net_return",
    "equity",
    "notional",
    "pnl",
    "gross_exposure",
    "net_exposure",
    "n_long",
    "n_short",
]


def live_dir(base_dir: Path | None = None) -> Path:
    return Path(base_dir) if base_dir is not None else data_root() / "live"


@dataclass
class DayRecord:
    date: pd.Timestamp
    gross_return: float
    turnover: float
    cost: float
    net_return: float
    equity: float
    notional: float
    pnl: float
    gross_exposure: float
    net_exposure: float
    n_long: int
    n_short: int

    def as_row(self) -> dict:
        return {k: getattr(self, k) for k in LEDGER_COLUMNS}


class LivePortfolio:
    """Incremental paper book. Load existing state or start a flat one, then
    call `record_day` once per trading day and `save` to persist."""

    def __init__(
        self,
        *,
        initial_notional: float = DEFAULT_NOTIONAL,
        cost_bps: float = COST_BPS,
        base_dir: Path | None = None,
        targets: pd.DataFrame | None = None,
        ledger: pd.DataFrame | None = None,
    ) -> None:
        self.initial_notional = float(initial_notional)
        self.cost_bps = float(cost_bps)
        self.base_dir = live_dir(base_dir)
        self.targets = targets if targets is not None else pd.DataFrame()
        self.ledger = ledger if ledger is not None else pd.DataFrame(columns=LEDGER_COLUMNS)

    # ---- persistence ----
    @property
    def targets_path(self) -> Path:
        return self.base_dir / "targets.parquet"

    @property
    def ledger_path(self) -> Path:
        return self.base_dir / "ledger.parquet"

    @property
    def meta_path(self) -> Path:
        return self.base_dir / "meta.json"

    @classmethod
    def load_or_create(
        cls,
        *,
        initial_notional: float = DEFAULT_NOTIONAL,
        cost_bps: float = COST_BPS,
        base_dir: Path | None = None,
    ) -> LivePortfolio:
        d = live_dir(base_dir)
        meta_path = d / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            targets = (
                pd.read_parquet(d / "targets.parquet")
                if (d / "targets.parquet").exists()
                else pd.DataFrame()
            )
            ledger = (
                pd.read_parquet(d / "ledger.parquet")
                if (d / "ledger.parquet").exists()
                else pd.DataFrame(columns=LEDGER_COLUMNS)
            )
            return cls(
                initial_notional=meta["initial_notional"],
                cost_bps=meta["cost_bps"],
                base_dir=base_dir,
                targets=targets,
                ledger=ledger,
            )
        return cls(initial_notional=initial_notional, cost_bps=cost_bps, base_dir=base_dir)

    def save(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.targets.empty:
            self.targets.to_parquet(self.targets_path)
        if not self.ledger.empty:
            self.ledger.to_parquet(self.ledger_path)
        meta = {
            "initial_notional": self.initial_notional,
            "cost_bps": self.cost_bps,
            "created_at": self._created_at(),
            "updated_at": datetime.now(UTC).isoformat(),
            "last_processed_date": (
                self.last_processed_date().isoformat() if self.last_processed_date() else None
            ),
            "n_days": len(self.ledger),
        }
        self.meta_path.write_text(json.dumps(meta, indent=2))

    def _created_at(self) -> str:
        if self.meta_path.exists():
            try:
                return json.loads(self.meta_path.read_text())["created_at"]
            except (KeyError, json.JSONDecodeError):
                pass
        return datetime.now(UTC).isoformat()

    # ---- queries ----
    def last_processed_date(self) -> pd.Timestamp | None:
        if self.ledger.empty:
            return None
        return pd.Timestamp(self.ledger.index.max())

    def has_date(self, date: pd.Timestamp | str) -> bool:
        return not self.ledger.empty and pd.Timestamp(date) in self.ledger.index

    def current_equity(self) -> float:
        if self.ledger.empty:
            return 1.0
        return float(self.ledger["equity"].iloc[-1])

    # ---- the one mutation ----
    def record_day(
        self,
        date: pd.Timestamp | str,
        returns_row: pd.Series,
        target: pd.Series,
    ) -> DayRecord:
        """Mark the held book to today's return, charge the cost of the most
        recent rebalance, then store today's new target.

        `returns_row` : simple close-to-close returns on `date`, per asset.
        `target`      : the new target weights computed at the close of `date`
                        (held starting the next trading day).
        """
        date = pd.Timestamp(date)
        if self.has_date(date):
            raise ValueError(f"{date.date()} already recorded; record_day is not idempotent")

        assets = self.targets.columns.union(target.index) if not self.targets.empty else target.index
        held = self._row_at(-1, assets)        # W[t-1] -- the book we held through `date`
        prev = self._row_at(-2, assets)        # W[t-2] -- to price the last rebalance
        r = returns_row.reindex(assets).fillna(0.0).astype(float)

        gross = float((held * r).sum())
        turnover = float((held - prev).abs().sum())
        cost = self.cost_bps / 1e4 * turnover
        net = gross - cost

        prev_equity = self.current_equity()
        equity = prev_equity * (1.0 + net)
        prev_notional = self.initial_notional * prev_equity
        notional = self.initial_notional * equity

        tgt = target.reindex(assets).fillna(0.0).astype(float)
        rec = DayRecord(
            date=date,
            gross_return=gross,
            turnover=turnover,
            cost=cost,
            net_return=net,
            equity=equity,
            notional=notional,
            pnl=notional - prev_notional,
            gross_exposure=float(tgt.abs().sum()),
            net_exposure=float(tgt.sum()),
            n_long=int((tgt > 0).sum()),
            n_short=int((tgt < 0).sum()),
        )

        # Append today's target (reindexed so the panel keeps one column set).
        self.targets = pd.concat(
            [self.targets.reindex(columns=assets), tgt.to_frame(name=date).T]
        )
        self.targets.index = pd.DatetimeIndex(self.targets.index)
        # Build the row fresh (not via the empty object-dtype seed) so the
        # ledger stays numeric float64/int64 rather than object.
        new_row = pd.DataFrame([rec.as_row()], index=pd.DatetimeIndex([date]))
        self.ledger = new_row if self.ledger.empty else pd.concat([self.ledger, new_row])
        return rec

    def _row_at(self, pos: int, assets: pd.Index) -> pd.Series:
        """Target row by negative position (-1 = most recent), zeros if absent."""
        if self.targets.empty or len(self.targets) < abs(pos):
            return pd.Series(0.0, index=assets)
        return self.targets.iloc[pos].reindex(assets).fillna(0.0).astype(float)
