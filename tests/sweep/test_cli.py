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
