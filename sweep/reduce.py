"""The reducer: every cell's file folded into one table, as the ``sweep-reduce`` command."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def reduce_cells(cells: Path) -> pa.Table:
    """Concatenate every Parquet file under a directory, sorted by distance then noise.

    Raises:
        FileNotFoundError: When the directory holds no cell files.
    """
    files = sorted(cells.glob("*.parquet"))
    if not files:
        msg = f"no cell files under {cells}"
        raise FileNotFoundError(msg)
    # Cells from before stage 8 lack the timing columns; they fold in as nulls.
    table = pa.concat_tables([pq.read_table(f) for f in files], promote_options="default")
    return table.sort_by([("distance", "ascending"), ("noise", "ascending")])


def main(argv: Sequence[str] | None = None) -> int:
    """Reduce a directory of cells into one Parquet file and print what was folded.

    Args:
        argv: ``<cells dir> <out file>``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when there are no cells.
    """
    parser = argparse.ArgumentParser(prog="sweep-reduce", description="fold cell files into one")
    parser.add_argument("cells", type=Path, help="directory of per-cell Parquet files")
    parser.add_argument("out", type=Path, help="Parquet file to write")
    args = parser.parse_args(argv)
    try:
        table = reduce_cells(args.cells)
    except FileNotFoundError as error:
        print(f"sweep-reduce: {error}", file=sys.stderr)
        return 2
    pq.write_table(table, args.out)
    print(f"{table.num_rows} cells -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
