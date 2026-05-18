"""statarb: systematic energy-commodities research platform.

See PLAN.md for the full project roadmap. The package is organized so that
each phase of the plan maps onto a subpackage:

- data:       loaders + point-in-time enforcement
- signals:    signal definitions (pure functions: prices -> scores)
- backtest:   the backtesting engine
- portfolio:  weighting + optimization
- costs:      transaction-cost models
- evaluation: metrics, walk-forward, regime analysis
- cli:        ingestion + run scripts
"""

__version__ = "0.0.1"
