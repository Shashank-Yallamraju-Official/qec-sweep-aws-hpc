import json
from pathlib import Path

import pytest

from mpi.plot import efficiency, main, records


def write_records(directory: Path) -> None:
    for nodes, total, exchange in [(1, 10.0, 1.0), (2, 8.0, 3.0), (4, 6.0, 4.0)]:
        record = {
            "qubits": 25,
            "layers": 6,
            "ranks": 2 * nodes,
            "kernel": "native",
            "gates": {"local": 10, "far": 3},
            "seconds": {"total": total, "compute": total - exchange, "exchange": exchange},
            "norm": 1.0,
        }
        (directory / f"nodes{nodes}.json").write_text(json.dumps(record))


def test_records_come_in_order_of_size(tmp_path: Path) -> None:
    write_records(tmp_path)
    assert [r["ranks"] for r in records(tmp_path)] == [2, 4, 8]


def test_efficiency_is_against_the_smallest_run(tmp_path: Path) -> None:
    write_records(tmp_path)
    assert [round(e) for e in efficiency(records(tmp_path))] == [100, 62, 42]


def test_the_command_draws_a_png_and_says_what_it_drew(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_records(tmp_path)
    out = tmp_path / "strong.png"
    assert main([str(tmp_path), str(out)]) == 0
    assert out.stat().st_size > 1000
    assert capsys.readouterr().out.strip() == f"3 node counts, 1 to 4 -> {out}"


def test_an_empty_directory_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path), str(tmp_path / "strong.png")]) == 2
    assert "no nodes*.json" in capsys.readouterr().err
