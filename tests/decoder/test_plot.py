import json
from pathlib import Path

import pyarrow as pa
import pytest

from decoder.plot import main, plot, summary
from results.compare import compare
from results.run import read_cells
from results.store import locate
from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.parquet import write

ERRORS = {
    # (distance, noise): (matching errors, learned errors); the learned decoder wins at d=5.
    (3, 0.001): (50, 48),
    (3, 0.002): (200, 190),
    (5, 0.001): (20, 10),
    (5, 0.002): (160, 100),
}


@pytest.fixture
def runs(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "evaluations"
    sides = {"pymatching": root / "a", "learned": root / "b"}
    for index, (decoder, run) in enumerate(sides.items()):
        for (distance, noise), errors in ERRORS.items():
            cell = Cell(distance=distance, noise=noise, shots=100_000)
            result = CellResult(
                cell=cell,
                errors=errors[index],
                seconds=1.0,
                seed=0,
                decoder=decoder,
                noise_model="correlated",
            )
            write(result, run)
        record = {"run": run.name, "queue": "sweep", "submitted": "2026-11-03T00:00:00Z"}
        (run / "run.json").write_text(json.dumps(record))
    return sides["pymatching"], sides["learned"]


def cells(run: Path) -> pa.Table:
    store, key = locate(str(run))
    return read_cells(store, key)


def test_plot_writes_a_png(runs: tuple[Path, Path], tmp_path: Path) -> None:
    matching, learned = runs
    out = tmp_path / "plots" / "decoders.png"
    drawn = plot(compare(cells(matching), cells(learned)), "correlated", out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert drawn == (2, 2)


def test_summary_gives_the_ratio_per_distance_and_the_verdicts(runs: tuple[Path, Path]) -> None:
    matching, learned = runs
    text = summary(compare(cells(matching), cells(learned)))
    assert (
        text.splitlines()[0] == "d=3: learned/matching 0.96 at p=0.001, 0.95 at p=0.002; 2 within"
    )
    assert (
        text.splitlines()[1]
        == "d=5: learned/matching 0.50 at p=0.001, 0.62 at p=0.002; 1 lower; 1 within"
    )


def test_main_draws_two_runs_and_prints_the_summary(
    runs: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    matching, learned = runs
    out = tmp_path / "decoders.png"
    assert main([str(matching), str(learned), "--out", str(out)]) == 0
    assert out.exists()
    printed = capsys.readouterr().out
    assert "d=5: learned/matching 0.50" in printed
    assert printed.rstrip().endswith(str(out))


def test_main_refuses_runs_that_share_no_cell(
    runs: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    matching, _ = runs
    other = tmp_path / "evaluations" / "c"
    write(CellResult(cell=Cell(7, 0.001, 10), errors=1, seconds=1.0, seed=0), other)
    (other / "run.json").write_text(
        '{"run": "c", "queue": "sweep", "submitted": "2026-11-03T00:00:00Z"}'
    )
    assert main([str(matching), str(other), "--out", str(tmp_path / "x.png")]) == 2
    assert "no cell" in capsys.readouterr().err
