from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from sweep.cell import Cell
from sweep.decode import CellResult


def write(result: CellResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.cell.name}.parquet"
    # A reclaimed node must not leave a half-written file under the cell's name.
    partial = path.with_name(path.name + ".partial")
    pq.write_table(pa.Table.from_pylist([_row(result)]), partial)
    partial.replace(path)
    return path


def read(path: Path) -> CellResult:
    row = pq.read_table(path).to_pylist()[0]
    cell = Cell(distance=row["distance"], noise=row["noise"], shots=row["shots"])
    return CellResult(cell=cell, errors=row["errors"], seconds=row["seconds"], seed=row["seed"])


def _row(result: CellResult) -> dict[str, int | float]:
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
    }
