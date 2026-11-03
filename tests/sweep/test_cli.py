from pathlib import Path

import pytest

from sweep.cli import main
from sweep.parquet import read


def test_main_writes_file_named_by_cell(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--d", "3", "--p", "1e-2", "--shots", "200", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "d3_p0.01_s200.parquet"
    assert expected.exists()
    assert capsys.readouterr().out.strip() == str(expected)


def test_main_reports_invalid_cell(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--d", "4", "--p", "0.01", "--shots", "10", "--out", str(tmp_path)]) == 2
    assert "odd" in capsys.readouterr().err


def test_main_runs_a_grid_cell_by_index(tmp_path: Path) -> None:
    assert main(["--index", "199", "--out", str(tmp_path)]) == 0
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


def test_main_decodes_under_a_named_noise_model(tmp_path: Path) -> None:
    argv = ["--d", "3", "--p", "1e-2", "--shots", "200", "--out", str(tmp_path)]
    assert main([*argv, "--noise", "correlated"]) == 0
    assert read(tmp_path / "d3_p0.01_s200.parquet").noise_model == "correlated"


def test_main_requires_a_model_for_the_learned_decoder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--d", "3", "--p", "1e-2", "--shots", "200", "--out", str(tmp_path)]
    assert main([*argv, "--decoder", "learned"]) == 2
    assert "--model" in capsys.readouterr().err


def test_main_refuses_a_model_beside_matching(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--d", "3", "--p", "1e-2", "--shots", "200", "--out", str(tmp_path)]
    assert main([*argv, "--model", str(tmp_path / "decoder.pt")]) == 2
    assert "learned" in capsys.readouterr().err
