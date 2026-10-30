from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.parquet import read, write

STARTED = datetime(2026, 10, 30, 12, 0, 0, 250_000, tzinfo=UTC)
RESULT = CellResult(
    cell=Cell(distance=5, noise=1e-3, shots=100_000),
    errors=7,
    seconds=1.5,
    seed=3,
    started=STARTED,
    host="node-1",
)


def test_write_names_file_by_cell(tmp_path: Path) -> None:
    assert write(RESULT, tmp_path / "results") == tmp_path / "results" / "d5_p0.001_s100000.parquet"


def test_round_trip_preserves_result(tmp_path: Path) -> None:
    assert read(write(RESULT, tmp_path)) == RESULT


def test_write_twice_overwrites(tmp_path: Path) -> None:
    write(RESULT, tmp_path)
    path = write(RESULT, tmp_path)
    assert pq.read_table(path).num_rows == 1


def test_columns_are_flat_and_named(tmp_path: Path) -> None:
    assert pq.read_table(write(RESULT, tmp_path)).column_names == [
        "distance",
        "noise",
        "shots",
        "errors",
        "logical_error_rate",
        "ci_low",
        "ci_high",
        "seconds",
        "seed",
        "started",
        "finished",
        "host",
    ]


def test_finished_is_the_start_plus_the_seconds_in_utc(tmp_path: Path) -> None:
    row = pq.read_table(write(RESULT, tmp_path)).to_pylist()[0]
    assert row["finished"] == STARTED + timedelta(seconds=1.5)
    assert row["finished"].tzinfo is not None


def test_a_failed_write_leaves_nothing_under_the_cell_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def partial_write(_table: object, where: Path) -> None:
        where.write_bytes(b"PAR1 truncated")
        raise OSError("node reclaimed")

    monkeypatch.setattr("sweep.parquet.pq.write_table", partial_write)
    with pytest.raises(OSError, match="reclaimed"):
        write(RESULT, tmp_path)
    assert not (tmp_path / "d5_p0.001_s100000.parquet").exists()
