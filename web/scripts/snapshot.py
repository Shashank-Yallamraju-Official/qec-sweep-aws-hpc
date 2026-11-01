"""Snapshot a store into the files the site reads: the catalogue and each sweep run's cells.

usage: uv run web/scripts/snapshot.py <store> <out dir>

The site queries ``runs.parquet`` and ``cells/<run>.parquet`` with range requests, so
each file is written once and never rewritten in place; a rebuilt site ships a new set.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from results.catalogue import catalogue
from results.run import read_cells
from results.store import Store, open_store

WORKERS = 8


def snapshot(store: Store, out: Path) -> tuple[int, int]:
    """Write the catalogue and the cells of every sweep run that has any.

    Args:
        store: Where the runs live.
        out: Directory to write under; created if missing.

    Returns:
        How many runs the catalogue holds and how many had cells written.
    """
    runs = catalogue(store)
    (out / "cells").mkdir(parents=True, exist_ok=True)
    pq.write_table(runs, out / "runs.parquet")
    with_cells = [r for r in runs.to_pylist() if r["cells"] > 0]

    def write(row: dict[str, Any]) -> None:
        cells = read_cells(store, key_within(store, row["key"]))
        pq.write_table(cells, out / "cells" / f"{row['run']}.parquet")

    # A run is a few hundred small objects; the runs are fetched side by side.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(write, with_cells))
    return runs.num_rows, len(with_cells)


def key_within(store: Store, address: str) -> str:
    """A run's key inside the store, from the full address the catalogue gives it."""
    return address.removeprefix(store.uri("")).lstrip("/")


def main(argv: Sequence[str] | None = None) -> int:
    """Snapshot a store and say what was written.

    Returns:
        Exit status: 0 on success, 2 when the store holds no run.
    """
    parser = argparse.ArgumentParser(prog="snapshot", description="snapshot runs for the site")
    parser.add_argument("store", help="s3://bucket or a directory holding runs")
    parser.add_argument("out", type=Path, help="directory the site serves as data/")
    args = parser.parse_args(argv)
    runs, written = snapshot(open_store(args.store), args.out)
    if runs == 0:
        print(f"snapshot: no run under {args.store}", file=sys.stderr)
        return 2
    print(f"{runs} runs, {written} with cells -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
