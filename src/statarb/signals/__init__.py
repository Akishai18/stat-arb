"""Signal definitions and normalization utilities.

A signal is a pure function: it takes a price (or other input) panel and
returns a score panel of the same shape -- one score per asset per day.
Higher score = more long. The score at row t may use ONLY data at row t
or earlier; the backtest engine applies an additional one-day lag, so
authors do not pre-lag.

Phase 3: momentum. Phase 4: reversal + combination. Phase 5: carry
(ETF-vs-futures proxy). Phase 6: COT positioning + EIA inventory surprise.
"""

from statarb.signals._normalize import cross_sectional_rank, cross_sectional_zscore
from statarb.signals.carry import realized_carry
from statarb.signals.combine import combine, sharpe_weighted_combine
from statarb.signals.cot import cot_positioning
from statarb.signals.inventory import inventory_surprise
from statarb.signals.momentum import momentum
from statarb.signals.reversal import reversal
from statarb.signals.ts_momentum import ts_momentum

__all__ = [
    "combine",
    "cot_positioning",
    "cross_sectional_rank",
    "cross_sectional_zscore",
    "inventory_surprise",
    "momentum",
    "realized_carry",
    "reversal",
    "sharpe_weighted_combine",
    "ts_momentum",
]
