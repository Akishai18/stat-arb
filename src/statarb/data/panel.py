"""PriceData: point-in-time-safe view over the adjusted-close panel.

The single rule this class enforces: never return a row dated after `as_of`.
Every signal and backtest call goes through here so that lookahead bugs are
impossible by construction. If you need data, you ask for it as-of a date.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from statarb.data.paths import processed_path

ReturnKind = Literal["simple", "log"]


class PriceData:
    def __init__(self, adj_close: pd.DataFrame) -> None:
        if not isinstance(adj_close.index, pd.DatetimeIndex):
            raise TypeError("adj_close must be indexed by DatetimeIndex")
        if not adj_close.index.is_monotonic_increasing:
            adj_close = adj_close.sort_index()
        self._adj_close = adj_close

    @classmethod
    def load(cls, path: Path | None = None) -> PriceData:
        path = path or processed_path("adj_close")
        if not Path(path).exists():
            raise FileNotFoundError(
                f"no processed adj_close at {path}. "
                "Run `python -m statarb.cli.ingest` to build it."
            )
        return cls(pd.read_parquet(path))

    @property
    def tickers(self) -> list[str]:
        return list(self._adj_close.columns)

    def _slice(self, as_of: pd.Timestamp | str | None) -> pd.DataFrame:
        if as_of is None:
            return self._adj_close
        ts = pd.Timestamp(as_of)
        return self._adj_close.loc[:ts]

    def adj_close(self, as_of: pd.Timestamp | str | None = None) -> pd.DataFrame:
        """Adjusted close panel up to and including `as_of`.

        `as_of=None` returns the full panel (useful for offline exploration;
        backtests should always pass a date).
        """
        return self._slice(as_of).copy()

    def returns(
        self,
        as_of: pd.Timestamp | str | None = None,
        *,
        kind: ReturnKind = "simple",
    ) -> pd.DataFrame:
        """Daily returns up to and including `as_of`.

        Simple returns from pct_change(); log returns from log(1+r). NaN
        propagates where a prior close is missing (no forward-fill).
        """
        prices = self._slice(as_of)
        simple = prices.pct_change()
        if kind == "simple":
            return simple
        if kind == "log":
            return np.log1p(simple)
        raise ValueError(f"unknown return kind: {kind!r}")
