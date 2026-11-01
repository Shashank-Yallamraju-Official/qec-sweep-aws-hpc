"""Snapshot a store into the files the site reads: the catalogue and each sweep run's cells.

usage: uv run web/scripts/snapshot.py <store> <out dir>

The site queries ``runs.parquet`` and ``cells/<run>.parquet`` with range requests, so
each file is written once and never rewritten in place; a rebuilt site ships a new set.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pyarrow.parquet as pq

from results.catalogue import catalogue
from results.run import read_cells
from results.store import Store, open_store


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
    written = 0
    for row in runs.to_pylist():
        if row["kind"] != "sweeps" or row["cells"] == 0:
            continue
        cells = read_cells(store, f"{row['kind']}/{row['run']}")
        pq.write_table(cells, out / "cells" / f"{row['run']}.parquet")
        written += 1
    return runs.num_rows, written


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
