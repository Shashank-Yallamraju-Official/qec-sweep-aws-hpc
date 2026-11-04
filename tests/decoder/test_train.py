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
from decoder.train import Training, World, load_samples, main, score, split, train  # noqa: E402
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
    write(sample(CELL, seed=2), samples)  # three files over two ranks: one holds two
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
    assert written["shots"] == 450
    assert written["held_out"] == 45
    assert written["epoch_losses"][-1] < written["epoch_losses"][0]
    assert load(out / "decoder.pt").hidden == 8


def test_a_single_process_records_one_rank(samples: Path, tmp_path: Path) -> None:
    record = train(samples, tmp_path / "model", epochs=1, hidden=8, layers=1)
    assert record.ranks == 1


def test_split_holds_a_tenth_of_this_ranks_shots_out() -> None:
    detectors = torch.zeros((101, 2, 3), dtype=torch.uint8)
    flips = torch.zeros(101, dtype=torch.uint8)
    (training, _), (held, _) = split(detectors, flips, 0)
    assert len(held) == 10
    assert len(training) == 91


def test_each_rank_loads_only_its_share_of_the_files(samples: Path) -> None:
    write(sample(CELL, seed=2), samples)
    names = tuple(sorted(p.name for p in samples.glob("*.npz")))
    _, first_names, first, _ = load_samples(samples, World(0, 2))
    _, second_names, second, _ = load_samples(samples, World(1, 2))
    assert first_names == second_names == names
    assert len(first) == 300
    assert len(second) == 150


def test_load_samples_refuses_fewer_files_than_ranks(samples: Path) -> None:
    with pytest.raises(ValueError, match="fewer"):
        load_samples(samples, World(0, 3))


def test_train_stops_when_the_held_out_loss_stalls(samples: Path, tmp_path: Path) -> None:
    record = train(
        samples, tmp_path / "model", seed=1, epochs=40, patience=1, hidden=8, layers=1, batch=32
    )
    assert record.max_epochs == 40
    assert record.patience == 1
    assert record.epochs < 40
    assert len(record.held_out_losses) == record.epochs == len(record.epoch_losses)
    assert record.held_out_loss == pytest.approx(min(record.held_out_losses))


def test_train_without_patience_runs_every_epoch(samples: Path, tmp_path: Path) -> None:
    record = train(samples, tmp_path / "model", epochs=3, hidden=8, layers=1)
    assert record.patience is None
    assert record.epochs == record.max_epochs == 3


def test_score_in_batches_is_the_one_pass_score(samples: Path, tmp_path: Path) -> None:
    train(samples, tmp_path / "model", epochs=1, hidden=8, layers=1)
    model = load(tmp_path / "model" / "decoder.pt")
    shots = sample(CELL, seed=9)
    detectors, flips = torch.from_numpy(shots.detectors), torch.from_numpy(shots.flips)
    assert score(model, detectors, flips, batch=7) == pytest.approx(score(model, detectors, flips))


def test_main_takes_a_patience(samples: Path, tmp_path: Path) -> None:
    out = tmp_path / "model"
    argv = ["--samples", str(samples), "--out", str(out), "--epochs", "30", "--patience", "1"]
    assert main([*argv, "--hidden", "8", "--layers", "1"]) == 0
    assert json.loads((out / "train.json").read_text())["patience"] == 1
