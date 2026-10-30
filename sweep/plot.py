"""Logical error rate against noise, one line per distance: the ``sweep-plot`` command."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib as mpl
import pyarrow as pa
import pyarrow.parquet as pq

mpl.use("Agg")
import matplotlib.pyplot as plt  # the backend must be chosen before this import


def drawable(rows: Sequence[dict[str, Any]], distance: int) -> list[dict[str, Any]]:
    """The rows of one distance that have a point on a log axis: those with at least one error."""
    return [r for r in rows if r["distance"] == distance and r["errors"] > 0]


def plot(table: pa.Table, out: Path) -> tuple[int, int]:
    """Draw the threshold plot: logical error rate against physical, log-log, per distance.

    Error bars are the Wilson interval. Cells with no observed errors have no
    point on a log axis and are left out.

    Args:
        table: Rows as ``sweep-reduce`` writes them.
        out: PNG path to write.

    Returns:
        How many distances and how many noise rates were drawn.
    """
    rows = table.to_pylist()
    distances = sorted({r["distance"] for r in rows})
    fig, ax = plt.subplots(figsize=(7, 5))
    for distance in distances:
        series = sorted(drawable(rows, distance), key=lambda r: r["noise"])
        rates = [r["logical_error_rate"] for r in series]
        below = [r["logical_error_rate"] - r["ci_low"] for r in series]
        above = [r["ci_high"] - r["logical_error_rate"] for r in series]
        ax.errorbar(
            [r["noise"] for r in series],
            rates,
            yerr=[below, above],
            marker="o",
            markersize=3,
            linewidth=1,
            capsize=2,
            label=f"d = {distance}",
        )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("physical error rate p")
    ax.set_ylabel("logical error rate per shot")
    ax.set_title(f"Rotated surface code, {rows[0]['shots']:,} shots per cell")
    ax.grid(visible=True, which="both", alpha=0.3)
    ax.legend()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return len(distances), len({r["noise"] for r in rows})


def main(argv: Sequence[str] | None = None) -> int:
    """Plot a reduced table to a PNG and print what was drawn.

    Args:
        argv: ``<table file> <png file>``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status 0.
    """
    parser = argparse.ArgumentParser(prog="sweep-plot", description="draw the threshold plot")
    parser.add_argument("table", type=Path, help="Parquet file from sweep-reduce")
    parser.add_argument("out", type=Path, help="PNG file to write")
    args = parser.parse_args(argv)
    distances, rates = plot(pq.read_table(args.table), args.out)
    print(f"{distances} distances, {rates} noise rates -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
