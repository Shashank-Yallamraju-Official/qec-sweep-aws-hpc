from pathlib import Path

import pytest

from sweep.cli import main


def test_main_writes_file_named_by_cell(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--d", "3", "--p", "1e-2", "--shots", "200", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "d3_p0.01_s200.parquet"
    assert expected.exists()
    assert capsys.readouterr().out.strip() == str(expected)


def test_main_reports_invalid_cell(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--d", "4", "--p", "0.01", "--shots", "10", "--out", str(tmp_path)]) == 2
    assert "odd" in capsys.readouterr().err


def test_main_runs_a_grid_cell_by_index(tmp_path: Path) -> None:
    assert main(["--index", "0", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "d3_p0.001_s100000.parquet").exists()


def test_main_rejects_an_index_beside_an_explicit_cell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(["--index", "7", "--d", "9", "--p", "0.01", "--shots", "10", "--out", str(tmp_path)])
        == 2
    )
    assert "by itself" in capsys.readouterr().err


def test_main_rejects_an_index_past_the_grid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--index", "200", "--out", str(tmp_path)]) == 2
    assert "200 cells" in capsys.readouterr().err
