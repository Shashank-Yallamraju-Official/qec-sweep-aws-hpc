from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from decoder.evaluate import decode  # noqa: E402
from decoder.model import load  # noqa: E402
from decoder.sample import sample, write  # noqa: E402
from decoder.train import train  # noqa: E402
from sweep.cell import Cell  # noqa: E402
from sweep.cli import main  # noqa: E402
from sweep.decode import CellResult  # noqa: E402
from sweep.parquet import read  # noqa: E402

CELL = Cell(distance=3, noise=0.05, shots=200)


@pytest.fixture(scope="module")
def model(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("trained")
    write(sample(CELL, seed=0), root / "samples")
    train(root / "samples", root / "model", epochs=2, hidden=8, layers=1)
    return root / "model" / "decoder.pt"


def test_decode_scores_a_cell_with_the_model(model: Path) -> None:
    result = decode(CELL, model, seed=9)
    assert isinstance(result, CellResult)
    assert result.decoder == "learned"
    assert result.cell == CELL
    assert 0 <= result.errors <= CELL.shots
    assert result.seed == 9
    assert result.seconds > 0


def test_decode_counts_the_shots_the_model_calls_wrong(model: Path) -> None:
    samples = sample(CELL, seed=9)
    flips = load(model).predict(torch.from_numpy(samples.detectors)).numpy()
    expected = int(np.sum(flips != samples.flips))
    assert decode(CELL, model, seed=9).errors == expected


def test_decode_takes_the_same_shots_in_batches(model: Path) -> None:
    assert decode(CELL, model, seed=9, batch=64).errors == decode(CELL, model, seed=9).errors


def test_decode_under_correlated_noise_samples_that_model(model: Path) -> None:
    samples = sample(CELL, seed=4, noise="correlated")
    flips = load(model).predict(torch.from_numpy(samples.detectors)).numpy()
    expected = int(np.sum(flips != samples.flips))
    assert decode(CELL, model, seed=4, noise="correlated").errors == expected


def test_decode_refuses_a_model_of_another_distance(model: Path) -> None:
    with pytest.raises(ValueError, match="distance"):
        decode(Cell(distance=5, noise=0.05, shots=10), model)


def test_the_sweep_command_decodes_a_cell_with_the_model(model: Path, tmp_path: Path) -> None:
    argv = ["--d", "3", "--p", "0.05", "--shots", "200", "--seed", "9", "--out", str(tmp_path)]
    assert (
        main([*argv, "--decoder", "learned", "--model", str(model), "--noise", "correlated"]) == 0
    )
    result = read(tmp_path / "d3_p0.05_s200.parquet")
    assert result.decoder == "learned"
    assert result.noise_model == "correlated"
    assert result.errors == decode(CELL, model, seed=9, noise="correlated").errors
