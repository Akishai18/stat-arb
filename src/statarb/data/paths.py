"""Resolve on-disk locations for raw and processed data.

Override the data root with STATARB_DATA_DIR. Otherwise defaults to
<cwd>/data, which assumes scripts run from the repo root.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    override = os.environ.get("STATARB_DATA_DIR")
    return Path(override) if override else Path.cwd() / "data"


def raw_dir() -> Path:
    p = data_root() / "raw"
    p.mkdir(parents=True, exist_ok=True)
    return p


def processed_dir() -> Path:
    p = data_root() / "processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def raw_path(ticker: str) -> Path:
    # ^VIX -> _VIX so the filename is portable
    safe = ticker.replace("^", "_")
    return raw_dir() / f"{safe}.parquet"


def processed_path(name: str) -> Path:
    return processed_dir() / f"{name}.parquet"
