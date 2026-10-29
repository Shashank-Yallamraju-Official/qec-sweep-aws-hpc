from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from sweep.cell import Cell
from sweep.decode import CellResult


def write(result: CellResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result.cell.name}.parquet"
    low, high = result.interval
    pq.write_table(pa.Table.from_pylist([_row(result, low, high)]), path)
    return path


def read(path: Path) -> CellResult:
    row = pq.read_table(path).to_pylist()[0]
    cell = Cell(distance=row["distance"], noise=row["noise"], shots=row["shots"])
    return CellResult(cell=cell, errors=row["errors"], seconds=row["seconds"], seed=row["seed"])


def _row(result: CellResult, low: float, high: float) -> dict[str, int | float]:
    cell = result.cell
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
