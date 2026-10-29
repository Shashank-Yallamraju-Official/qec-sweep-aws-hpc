from pathlib import Path

import pyarrow.parquet as pq
import pytest

from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.parquet import write
from sweep.plot import main, plot
from sweep.reduce import reduce_cells


@pytest.fixture
def table_path(tmp_path: Path) -> Path:
    cells = tmp_path / "cells"
    for distance in (3, 5):
        for noise, errors in ((0.001, 5), (0.003, 30), (0.01, 300)):
            cell = Cell(distance=distance, noise=noise, shots=10_000)
            write(CellResult(cell=cell, errors=errors * distance, seconds=1.0, seed=0), cells)
    path = tmp_path / "sweep.parquet"
    pq.write_table(reduce_cells(cells), path)
    return path


def test_plot_writes_a_png(table_path: Path, tmp_path: Path) -> None:
    out = tmp_path / "plot.png"
    plot(pq.read_table(table_path), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_main_reports_what_it_drew(
    table_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "plot.png"
    assert main([str(table_path), str(out)]) == 0
    assert capsys.readouterr().out.strip() == f"2 distances, 3 noise rates -> {out}"
