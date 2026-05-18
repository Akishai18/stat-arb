# stat-arb

Systematic energy-commodities research platform.

> Analyze commodity market data to identify statistical mispricings and exploit them through a systematic long/short portfolio.

See [`PLAN.md`](./PLAN.md) for the full phased implementation roadmap.

## Quickstart

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run pytest
uv run python -c "import statarb; print(statarb.__version__)"
```

## Layout

```
src/statarb/
  data/         # loaders, point-in-time price access
  signals/      # momentum, reversal, carry, inventory, COT
  backtest/     # vectorized no-lookahead engine
  portfolio/    # weighting + cvxpy optimization
  costs/        # transaction-cost models
  evaluation/   # metrics, walk-forward, regime analysis
  cli/          # ingestion + run scripts
reports/        # written research output
tests/
```

## Status

Phase 0 (foundation) complete. Phase 1 (data layer) next — see PLAN.md.
