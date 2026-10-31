"""Two runs cell by cell, different only where the intervals are apart: ``results-compare``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, get_args

import pyarrow as pa
import pyarrow.parquet as pq

from results.run import RunRecord, read_cells, read_record
from results.store import locate
from sweep.cell import Cell

Verdict = Literal["within", "lower", "higher"]
VERDICTS: tuple[Verdict, ...] = get_args(Verdict)


@dataclass(frozen=True)
class Side:
    """One run's result for a cell: the count and the interval it was written with."""

    errors: int
    rate: float
    low: float
    high: float


@dataclass(frozen=True)
class CellComparison:
    """One cell seen in both runs.

    Attributes:
        cell: The cell both runs decoded.
        a: The first run's result, the reference.
        b: The second run's result, the one being judged.
    """

    cell: Cell
    a: Side
    b: Side

    @property
    def ratio(self) -> float | None:
        """The judged rate over the reference rate; undefined when the reference saw no error."""
        return None if self.a.errors == 0 else self.b.rate / self.a.rate

    @property
    def verdict(self) -> Verdict:
        """Where b stands against a: ``lower`` or ``higher`` only with the intervals apart.

        Two 95% intervals that do not touch is a conservative test, stricter than
        the usual two-proportion one; a difference it calls is one that holds.
        """
        if self.b.high < self.a.low:
            return "lower"
        if self.b.low > self.a.high:
            return "higher"
        return "within"


@dataclass(frozen=True)
class Comparison:
    """Two runs joined on their cells.

    Attributes:
        cells: Every cell both runs decoded, in grid order.
        only_a: Cells the first run decoded and the second did not.
        only_b: Cells the second run decoded and the first did not.
    """

    cells: tuple[CellComparison, ...]
    only_a: int
    only_b: int

    def count(self, verdict: Verdict) -> int:
        """How many shared cells got a verdict."""
        return sum(1 for c in self.cells if c.verdict == verdict)


def compare(a: pa.Table, b: pa.Table) -> Comparison:
    """Join two runs' cells on distance, noise and shots.

    Args:
        a: The reference run's cells, as ``sweep`` writes them.
        b: The cells of the run being judged.

    Returns:
        The shared cells with each side's result, and how many were on one side only.
    """
    sides_a = {_key(row): _side(row) for row in a.to_pylist()}
    sides_b = {_key(row): _side(row) for row in b.to_pylist()}
    shared = sorted(sides_a.keys() & sides_b.keys())
    cells = tuple(CellComparison(cell=Cell(*key), a=sides_a[key], b=sides_b[key]) for key in shared)
    return Comparison(cells, len(sides_a) - len(shared), len(sides_b) - len(shared))


def _key(row: dict[str, Any]) -> tuple[int, float, int]:
    return int(row["distance"]), float(row["noise"]), int(row["shots"])


def _side(row: dict[str, Any]) -> Side:
    return Side(int(row["errors"]), row["logical_error_rate"], row["ci_low"], row["ci_high"])


def as_table(comparison: Comparison) -> pa.Table:
    """The comparison as rows, one per shared cell, for a file or a query."""
    rows = [
        {
            "distance": c.cell.distance,
            "noise": c.cell.noise,
            "shots": c.cell.shots,
            "errors_a": c.a.errors,
            "errors_b": c.b.errors,
            "rate_a": c.a.rate,
            "rate_b": c.b.rate,
            "low_a": c.a.low,
            "high_a": c.a.high,
            "low_b": c.b.low,
            "high_b": c.b.high,
            "ratio": c.ratio,
            "verdict": c.verdict,
        }
        for c in comparison.cells
    ]
    return pa.Table.from_pylist(rows)


def summary(comparison: Comparison) -> str:
    """The verdict counts on one line, then one line per cell the intervals set apart."""
    counts = ", ".join(f"{comparison.count(v)} {v}" for v in VERDICTS)
    lines = [
        (
            f"{len(comparison.cells)} cells in both runs: {counts}; "
            f"{comparison.only_a} only in a, {comparison.only_b} only in b"
        )
    ]
    lines.extend(_line(c) for c in comparison.cells if c.verdict != "within")
    return "\n".join(lines)


def _line(c: CellComparison) -> str:
    ratio = "n/a" if c.ratio is None else f"{c.ratio:.2f}"
    return (
        f"  d={c.cell.distance} p={c.cell.noise}: a {c.a.rate:.3e} [{c.a.low:.3e}, {c.a.high:.3e}]"
        f"  b {c.b.rate:.3e} [{c.b.low:.3e}, {c.b.high:.3e}]  ratio {ratio}  {c.verdict}"
    )


def provenance(label: str, record: RunRecord) -> str:
    """One line naming what produced a run: its address, commit, digest and seed."""
    return (
        f"{label}: {record.key} commit {record.commit or '?'} "
        f"image {record.image_digest or '?'} seed {record.seed if record.seed is not None else '?'}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Compare two runs by address, print the verdicts and optionally write the rows.

    Args:
        argv: ``<run a> <run b> [--out file]``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when a run has no cells or the runs share none.
    """
    parser = argparse.ArgumentParser(
        prog="results-compare", description="judge run b against run a, cell by cell"
    )
    parser.add_argument("a", help="the reference run, s3://bucket/sweeps/<run> or a directory")
    parser.add_argument("b", help="the run being judged")
    parser.add_argument("--out", help="Parquet file for the comparison rows")
    args = parser.parse_args(argv)
    try:
        comparison = _compare_addresses(args.a, args.b)
    except FileNotFoundError as error:
        print(f"results-compare: {error}", file=sys.stderr)
        return 2
    if not comparison.cells:
        print("results-compare: the runs share no cell", file=sys.stderr)
        return 2
    print(summary(comparison))
    if args.out:
        pq.write_table(as_table(comparison), args.out)
        print(f"{len(comparison.cells)} rows -> {args.out}")
    return 0


def _compare_addresses(a: str, b: str) -> Comparison:
    (store_a, key_a), (store_b, key_b) = locate(a), locate(b)
    print(provenance("a", read_record(store_a, key_a)))
    print(provenance("b", read_record(store_b, key_b)))
    return compare(read_cells(store_a, key_a), read_cells(store_b, key_b))


if __name__ == "__main__":
    sys.exit(main())
