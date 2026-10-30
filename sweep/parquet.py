"""One Parquet file per cell, named by the cell, so tasks are idempotent and retryable."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from sweep.cell import Cell
from sweep.decode import CellResult


def write(result: CellResult, out_dir: Path) -> Path:
    """Write a result as a single-row Parquet file named by its cell.

    Args:
        result: What to write.
        out_dir: Directory for the file, created if missing.

    Returns:
        The path written, ``<out_dir>/<cell name>.parquet``; an existing file is replaced.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.cell.name}.parquet"
    # A reclaimed node must not leave a half-written file under the cell's name.
    partial = path.with_name(path.name + ".partial")
    pq.write_table(pa.Table.from_pylist([_row(result)]), partial)
    partial.replace(path)
    return path


def read(path: Path) -> CellResult:
    """Read back a file written by ``write()``.

    Raises:
        ValueError: For a file from before stage 8, which has no start, finish or host.
    """
    row = pq.read_table(path).to_pylist()[0]
    if "started" not in row:
        msg = f"{path} predates the timing columns; it has no start, finish or host"
        raise ValueError(msg)
    cell = Cell(distance=row["distance"], noise=row["noise"], shots=row["shots"])
    return CellResult(
        cell=cell,
        errors=row["errors"],
        seconds=row["seconds"],
        seed=row["seed"],
        started=row["started"],
        host=row["host"],
    )


def _row(result: CellResult) -> dict[str, int | float | str | datetime]:
    cell = result.cell
    low, high = result.interval
    return {
        "distance": cell.distance,
        "noise": cell.noise,
        "shots": cell.shots,
        "errors": result.errors,
        "logical_error_rate": result.logical_error_rate,
        "ci_low": low,
        "ci_high": high,
        "seconds": result.seconds,
        "seed": result.seed,
        "started": result.started,
        "finished": result.finished,
        "host": result.host,
    }
