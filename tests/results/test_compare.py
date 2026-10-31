from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from results.compare import CellComparison, Side, as_table, compare, main, summary
from results.run import read_cells
from results.store import LocalStore
from sweep.cell import Cell
from sweep.decode import wilson_interval


def cells(counts: dict[int, int], shots: int = 1000) -> pa.Table:
    rows = []
    for distance, errors in counts.items():
        low, high = wilson_interval(errors, shots)
        rows.append(
            {
                "distance": distance,
                "noise": 0.01,
                "shots": shots,
                "errors": errors,
                "logical_error_rate": errors / shots,
                "ci_low": low,
                "ci_high": high,
            }
        )
    return pa.Table.from_pylist(rows)


def test_compare_joins_on_the_cell_and_counts_the_rest() -> None:
    comparison = compare(cells({3: 30, 5: 10, 7: 2}), cells({3: 28, 5: 10, 9: 1}))
    assert [c.cell.distance for c in comparison.cells] == [3, 5]
    assert (comparison.only_a, comparison.only_b) == (1, 1)


def test_a_difference_inside_the_intervals_is_within() -> None:
    comparison = compare(cells({3: 30}), cells({3: 28}))
    assert comparison.cells[0].verdict == "within"
    assert comparison.cells[0].ratio == pytest.approx(28 / 30)


def test_intervals_apart_give_a_direction() -> None:
    comparison = compare(cells({3: 300, 5: 100}), cells({3: 100, 5: 300}))
    assert [c.verdict for c in comparison.cells] == ["lower", "higher"]
    assert (comparison.count("lower"), comparison.count("higher")) == (1, 1)


def test_the_ratio_is_undefined_when_the_reference_saw_no_error() -> None:
    side = Side(errors=0, rate=0.0, low=0.0, high=0.004)
    other = Side(errors=3, rate=0.003, low=0.001, high=0.009)
    assert CellComparison(Cell(3, 0.01, 1000), side, other).ratio is None


def test_the_summary_names_only_the_cells_set_apart() -> None:
    text = summary(compare(cells({3: 30, 5: 300}), cells({3: 28, 5: 100})))
    lines = text.splitlines()
    assert lines[0] == "2 cells in both runs: 1 within, 1 lower, 0 higher; 0 only in a, 0 only in b"
    assert len(lines) == 2
    assert lines[1].startswith("  d=5 p=0.01: a 3.000e-01")
    assert lines[1].endswith("ratio 0.33  lower")


def test_the_table_has_a_row_per_shared_cell() -> None:
    table = as_table(compare(cells({3: 30, 5: 10}), cells({3: 28, 5: 10})))
    assert table.num_rows == 2
    assert table.column("verdict").to_pylist() == ["within", "within"]


def test_the_command_prints_provenance_then_verdicts_and_writes_rows(
    store: LocalStore, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = store.uri("sweeps/20261030T001136Z"), store.uri("sweeps/20261030T231737Z")
    out = tmp_path / "comparison.parquet"
    assert main([a, b, "--out", str(out)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"a: {a} commit ? image ? seed ?"
    assert lines[1] == f"b: {b} commit 207f3e5 image sha256:9d217f8c seed 7"
    assert lines[2].startswith("2 cells in both runs: 2 within")
    assert lines[2].endswith("0 only in a, 1 only in b")
    assert lines[-1] == f"2 rows -> {out}"
    assert pq.read_table(out).num_rows == 2
    assert read_cells(store, "sweeps/20261030T231737Z").num_rows == 3


def test_the_command_reports_a_run_without_cells(
    store: LocalStore, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = store.uri("sweeps/20261030T001136Z"), store.uri("statevector/20261030T120000Z")
    assert main([a, b]) == 2
    assert "no cells under" in capsys.readouterr().err
