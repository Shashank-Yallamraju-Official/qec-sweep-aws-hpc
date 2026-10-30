import json
from pathlib import Path

import numpy as np
import pytest

from mpi.cli import main, run
from mpi.exchange import Alone, Exchange
from tests.mpi.lockstep import run as on_ranks


def test_the_record_names_the_run_and_the_time_went_somewhere(tmp_path: Path) -> None:
    out = tmp_path / "run.json"
    assert main(["--qubits", "4", "--layers", "2", "--out", str(out)], exchange=Alone()) == 0
    record = json.loads(out.read_text())
    assert (record["qubits"], record["layers"], record["ranks"]) == (4, 2, 1)
    assert record["gates"] == {"local": 8 + 2 + 1, "far": 0}
    assert record["seconds"]["compute"] > 0
    assert record["seconds"]["exchange"] == 0
    assert record["seconds"]["total"] >= record["seconds"]["compute"]
    assert np.isclose(record["norm"], 1)


def test_across_ranks_the_far_gates_are_counted_and_the_norm_is_kept() -> None:
    def body(exchange: Exchange) -> dict[str, object]:
        return run(4, 2, exchange)

    records = on_ranks(4, body)
    assert all(record == records[0] for record in records)
    assert records[0]["gates"] == {"local": 4 + 1, "far": 4 + 1 + 1}
    seconds = records[0]["seconds"]
    assert isinstance(seconds, dict)
    assert seconds["exchange"] > 0
    assert np.isclose(float(str(records[0]["norm"])), 1)


def test_too_many_ranks_for_the_qubits_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class Eight(Alone):
        size = 8

    status = main(["--qubits", "2", "--out", str(tmp_path / "run.json")], exchange=Eight())
    assert status == 2
    assert "at least 3 qubits" in capsys.readouterr().err
