from pathlib import Path

import pyarrow.parquet as pq
import pytest

from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.parquet import write
from sweep.reduce import main, reduce_cells


def results(cells: Path) -> None:
    for distance, noise, errors in [(5, 0.01, 50), (3, 0.01, 90), (3, 0.001, 2)]:
        cell = Cell(distance=distance, noise=noise, shots=1000)
        write(CellResult(cell=cell, errors=errors, seconds=0.5, seed=0), cells)


def test_reduce_cells_concatenates_every_file_sorted_by_distance_then_noise(tmp_path: Path) -> None:
    results(tmp_path)
    table = reduce_cells(tmp_path)
    assert table.num_rows == 3
    assert table.column("distance").to_pylist() == [3, 3, 5]
    assert table.column("noise").to_pylist() == [0.001, 0.01, 0.01]
    assert table.column("errors").to_pylist() == [2, 90, 50]


def test_reduce_cells_with_no_files_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no cell files"):
        reduce_cells(tmp_path)


def test_main_writes_one_parquet_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cells = tmp_path / "cells"
    results(cells)
    out = tmp_path / "sweep.parquet"
    assert main([str(cells), str(out)]) == 0
    assert pq.read_table(out).num_rows == 3
    assert capsys.readouterr().out.strip() == f"3 cells -> {out}"


def test_reduce_cells_folds_in_files_from_before_the_timing_columns(tmp_path: Path) -> None:
    results(tmp_path)
    old = pq.read_table(tmp_path / "d5_p0.01_s1000.parquet").drop_columns(
        ["started", "finished", "host"]
    )
    pq.write_table(old, tmp_path / "d5_p0.01_s1000.parquet")
    table = reduce_cells(tmp_path)
    assert table.num_rows == 3
    assert table.column("host").null_count == 1
