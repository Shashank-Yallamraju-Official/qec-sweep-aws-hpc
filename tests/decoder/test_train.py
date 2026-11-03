import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from decoder.model import load  # noqa: E402
from decoder.sample import sample, write  # noqa: E402
from decoder.train import Training, main, train  # noqa: E402
from sweep.cell import Cell  # noqa: E402

CELL = Cell(distance=3, noise=0.05, shots=150)


@pytest.fixture
def samples(tmp_path: Path) -> Path:
    out = tmp_path / "samples"
    for seed in (0, 1):
        write(sample(CELL, seed=seed), out)
    return out


def test_train_lowers_the_loss_and_records_what_it_did(samples: Path, tmp_path: Path) -> None:
    out = tmp_path / "model"
    record = train(samples, out, seed=3, epochs=4, learning_rate=0.01, batch=32, hidden=8, layers=1)
    assert isinstance(record, Training)
    assert record.cell == CELL
    assert record.samples == tuple(sorted(p.name for p in samples.glob("*.npz")))
    assert record.shots == 300
    assert record.held_out == 30
    assert record.epochs == 4
    assert record.epoch_losses[-1] < record.epoch_losses[0]
    assert 0 <= record.held_out_accuracy <= 1
    assert record.device == "cpu"
    assert record.seconds > 0
    assert record.torch == torch.__version__
    written = json.loads((out / "train.json").read_text())
    assert written["cell"] == {"distance": 3, "noise": 0.05, "shots": 150}
    assert written["seed"] == 3
    assert written["held_out_loss"] == pytest.approx(record.held_out_loss)


def test_train_saves_a_model_that_loads_and_predicts(samples: Path, tmp_path: Path) -> None:
    out = tmp_path / "model"
    train(samples, out, seed=0, epochs=1, hidden=8, layers=1)
    model = load(out / "decoder.pt")
    detectors = torch.from_numpy(sample(CELL, seed=9).detectors)
    assert model.predict(detectors).shape == (CELL.shots,)


def test_train_is_the_same_for_the_same_seed(samples: Path, tmp_path: Path) -> None:
    first = train(samples, tmp_path / "a", seed=5, epochs=2, hidden=8, layers=1)
    second = train(samples, tmp_path / "b", seed=5, epochs=2, hidden=8, layers=1)
    assert first.epoch_losses == second.epoch_losses


def test_train_refuses_samples_of_different_cells(samples: Path, tmp_path: Path) -> None:
    write(sample(Cell(5, 0.05, 20), seed=0), samples)
    with pytest.raises(ValueError, match="one cell"):
        train(samples, tmp_path / "model", epochs=1, hidden=8, layers=1)


def test_train_refuses_an_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(FileNotFoundError, match="no samples"):
        train(tmp_path / "empty", tmp_path / "model", epochs=1)


def test_main_trains_from_the_command_line(
    samples: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "model"
    argv = [
        "--samples",
        str(samples),
        "--out",
        str(out),
        "--epochs",
        "1",
        "--hidden",
        "8",
        "--layers",
        "1",
    ]
    assert main(argv) == 0
    assert (out / "train.json").exists()
    assert str(out / "train.json") in capsys.readouterr().out


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_two_ranks_train_one_model_between_them(samples: Path, tmp_path: Path) -> None:
    out = tmp_path / "model"
    port = str(free_port())
    argv = [sys.executable, "-m", "decoder.train", "--samples", str(samples), "--out", str(out)]
    argv += ["--epochs", "2", "--hidden", "8", "--layers", "1", "--batch", "32"]
    world = {"WORLD_SIZE": "2", "MASTER_ADDR": "127.0.0.1", "MASTER_PORT": port}
    ranks = [
        subprocess.Popen(
            argv, env={**os.environ, **world, "RANK": str(rank)}, stderr=subprocess.PIPE, text=True
        )
        for rank in range(2)
    ]
    for rank in ranks:
        assert rank.wait(timeout=120) == 0, rank.stderr.read()  # type: ignore[union-attr]
    written = json.loads((out / "train.json").read_text())
    assert written["ranks"] == 2
    assert written["shots"] == 300
    assert written["held_out"] == 30
    assert written["epoch_losses"][-1] < written["epoch_losses"][0]
    assert load(out / "decoder.pt").hidden == 8


def test_a_single_process_records_one_rank(samples: Path, tmp_path: Path) -> None:
    record = train(samples, tmp_path / "model", epochs=1, hidden=8, layers=1)
    assert record.ranks == 1
