"""Data-cleaning helpers for known anomalies.

The standard return-based backtest framework assumes prices are positive
and that `pct_change` produces a meaningful percent move. Both assumptions
break on 2020-04-20, when the WTI front-month contract closed at -$37.63
(the famous "negative oil" day). The same day's `pct_change` is -306%, and
the following day's recovery from negative-to-positive produces -126% --
neither is a sensible return for backtesting.

This module provides explicit, documented masking for events that fall
outside the assumptions of standard return-based reasoning. We don't
silently fix data; we either flag it as NaN and rely on the engine's
NaN-tolerance, or we leave it. There is no "auto-clean everything"
function -- every entry is auditable.

If you need to keep the raw record, don't call these helpers.
"""

from __future__ import annotations

import pandas as pd

# Each entry: (ticker, ISO date, reason). Edit history is the documentation.
KNOWN_ANOMALIES: list[tuple[str, str, str]] = [
    ("CL=F", "2020-04-20", "WTI front-month closed -$37.63 (negative oil); pct_change is -306%."),
    ("CL=F", "2020-04-21", "WTI front-month recovered from -$37 to +$10; pct_change is -126%."),
]


def mask_known_anomalies(adj_close: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `adj_close` with KNOWN_ANOMALIES set to NaN.

    Affected returns become NaN; the backtest engine treats NaN returns as
    contributing 0 to that day's P&L when holding the position.
    """
    out = adj_close.copy()
    for ticker, iso_date, _reason in KNOWN_ANOMALIES:
        if ticker not in out.columns:
            continue
        ts = pd.Timestamp(iso_date)
        if ts in out.index:
            out.loc[ts, ticker] = float("nan")
    return out
