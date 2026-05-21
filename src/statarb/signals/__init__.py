"""Signal definitions and normalization utilities.

A signal is a pure function: it takes a price (or other input) panel and
returns a score panel of the same shape -- one score per asset per day.
Higher score = more long. The score at row t may use ONLY data at row t
or earlier; the backtest engine applies an additional one-day lag, so
authors do not pre-lag.

Phase 3: momentum. Phase 4: reversal + combination. Phase 5: carry
(ETF-vs-futures proxy). Phase 6: inventory + COT positioning.
"""

from statarb.signals._normalize import cross_sectional_rank, cross_sectional_zscore
from statarb.signals.carry import realized_carry
from statarb.signals.combine import combine
from statarb.signals.momentum import momentum
from statarb.signals.reversal import reversal

__all__ = [
    "combine",
    "cross_sectional_rank",
    "cross_sectional_zscore",
    "momentum",
    "realized_carry",
    "reversal",
]
