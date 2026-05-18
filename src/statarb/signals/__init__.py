"""Signal definitions.

Each signal is a pure function mapping a prices/returns panel to a daily score
panel (one score per asset per day). Signals MUST only use data available
at or before the score's timestamp.

Phase 3: momentum. Phase 4: reversal. Phase 5: carry. Phase 6: inventory
surprise + COT positioning.
"""
