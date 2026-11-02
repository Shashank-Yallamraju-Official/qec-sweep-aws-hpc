"""Trains the recurrent decoder on a generate run's samples: the ``decoder-train`` command.

One call reads every ``.npz`` a generate run wrote for one cell, holds a tenth of
the shots back, fits the model by mini-batched Adam on the binary cross-entropy of
the observable flip, saves the model and writes a ``train.json`` beside it that
says what was trained on what, how well it did on the held-out shots, and where
and how long it ran. The device is a parameter so the same call moves to a GPU
queue the day one exists.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import Tensor, nn

from decoder.model import HIDDEN, LAYERS, RecurrentDecoder, build, save
from decoder.sample import read
from sweep.cell import Cell

MODEL = "decoder.pt"
RECORD = "train.json"
HELD_OUT = 0.1


@dataclass(frozen=True)
class Training:
    """What one training run did, as ``train.json`` records it.

    Attributes:
        cell: The cell every sample file was drawn from.
        samples: The sample files, by name, in the order they were read.
        shots: Shots across all the files.
        held_out: Shots kept back from training and scored at the end.
        seed: The seed that fixed the split, the initial weights and the batches.
        epochs: Passes over the training shots.
        learning_rate: Adam's step size.
        batch: Shots per step.
        epoch_losses: Mean training loss after each epoch.
        loss: Mean training loss after the last epoch.
        accuracy: Fraction of training shots the model calls right at the end.
        held_out_loss: Mean loss on the held-out shots.
        held_out_accuracy: Fraction of held-out shots the model calls right.
        device: The torch device the training ran on.
        seconds: Wall-clock seconds spent training.
        torch: The torch version.
    """

    cell: Cell
    samples: tuple[str, ...]
    shots: int
    held_out: int
    seed: int
    epochs: int
    learning_rate: float
    batch: int
    epoch_losses: tuple[float, ...]
    loss: float
    accuracy: float
    held_out_loss: float
    held_out_accuracy: float
    device: str
    seconds: float
    torch: str


def load_samples(samples_dir: Path) -> tuple[Cell, tuple[str, ...], Tensor, Tensor]:
    """Every sample file under a directory as one set of detectors and flips.

    Raises:
        FileNotFoundError: When the directory holds no sample file.
        ValueError: When the files were not all sampled from one cell.
    """
    paths = sorted(samples_dir.glob("*.npz"))
    if not paths:
        msg = f"no samples under {samples_dir}"
        raise FileNotFoundError(msg)
    loaded = [read(p) for p in paths]
    cells = {s.cell for s in loaded}
    if len(cells) != 1:
        msg = f"the samples under {samples_dir} are not of one cell: {sorted(map(str, cells))}"
        raise ValueError(msg)
    detectors = torch.from_numpy(np.concatenate([s.detectors for s in loaded]))
    flips = torch.from_numpy(np.concatenate([s.flips for s in loaded]))
    return loaded[0].cell, tuple(p.name for p in paths), detectors, flips


def score(model: RecurrentDecoder, detectors: Tensor, flips: Tensor) -> tuple[float, float]:
    """Mean loss and accuracy of the model on a set, without tracking gradients."""
    model.eval()
    with torch.no_grad():
        logits = model(detectors)
        loss = nn.functional.binary_cross_entropy_with_logits(logits, flips.to(torch.float32))
        accuracy = ((logits > 0).to(torch.uint8) == flips).to(torch.float32).mean()
    return float(loss), float(accuracy)


def train(  # noqa: PLR0913
    samples_dir: Path,
    out_dir: Path,
    *,
    seed: int = 0,
    epochs: int = 10,
    learning_rate: float = 1e-3,
    batch: int = 256,
    hidden: int = HIDDEN,
    layers: int = LAYERS,
    device: str = "cpu",
) -> Training:
    """Train a decoder on a directory of samples, save it and its record under ``out_dir``.

    The seed fixes everything that could differ between two runs on one machine:
    which shots are held out, the initial weights and the order of the batches.
    """
    started = time.perf_counter()
    cell, names, detectors, flips = load_samples(samples_dir)
    generator = torch.Generator().manual_seed(seed)
    order = torch.randperm(len(flips), generator=generator)
    held = round(len(flips) * HELD_OUT)
    held_idx, train_idx = order[:held], order[held:]
    where = torch.device(device)
    train_x, train_y = detectors[train_idx].to(where), flips[train_idx].to(where)
    held_x, held_y = detectors[held_idx].to(where), flips[held_idx].to(where)

    torch.manual_seed(seed)
    model = build(cell, hidden=hidden, layers=layers).to(where)
    optimiser = torch.optim.Adam(model.parameters(), lr=learning_rate)
    epoch_losses = []
    for _ in range(epochs):
        model.train()
        total = 0.0
        shuffled = torch.randperm(len(train_y), generator=generator)
        for rows in torch.split(shuffled, batch):
            optimiser.zero_grad()
            step_loss = nn.functional.binary_cross_entropy_with_logits(
                model(train_x[rows]), train_y[rows].to(torch.float32)
            )
            step_loss.backward()  # type: ignore[no-untyped-call]
            optimiser.step()
            total += step_loss.detach().item() * len(rows)
        epoch_losses.append(total / len(train_y))

    loss, accuracy = score(model, train_x, train_y)
    held_loss, held_accuracy = score(model, held_x, held_y)
    out_dir.mkdir(parents=True, exist_ok=True)
    save(model.to("cpu"), out_dir / MODEL)
    record = Training(
        cell=cell,
        samples=names,
        shots=len(flips),
        held_out=held,
        seed=seed,
        epochs=epochs,
        learning_rate=learning_rate,
        batch=batch,
        epoch_losses=tuple(epoch_losses),
        loss=loss,
        accuracy=accuracy,
        held_out_loss=held_loss,
        held_out_accuracy=held_accuracy,
        device=device,
        seconds=time.perf_counter() - started,
        torch=torch.__version__,
    )
    (out_dir / RECORD).write_text(json.dumps(asdict(record), indent=2))
    return record


def main(argv: Sequence[str] | None = None) -> int:
    """Train from the command line and print where the record went.

    Args:
        argv: ``--samples dir --out dir [--seed] [--epochs] [--learning-rate] [--batch]
            [--hidden] [--layers] [--device]``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when the samples cannot be trained on.
    """
    parser = argparse.ArgumentParser(
        prog="decoder-train", description="train the recurrent decoder on a generate run"
    )
    parser.add_argument("--samples", type=Path, required=True, help="a generate run's samples")
    parser.add_argument("--out", type=Path, required=True, help="directory for the model")
    parser.add_argument("--seed", type=int, default=0, help="split, weights and batch order")
    parser.add_argument("--epochs", type=int, default=10, help="passes over the training shots")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Adam's step size")
    parser.add_argument("--batch", type=int, default=256, help="shots per step")
    parser.add_argument("--hidden", type=int, default=HIDDEN, help="LSTM state size")
    parser.add_argument("--layers", type=int, default=LAYERS, help="stacked LSTM layers")
    parser.add_argument("--device", default="cpu", help="torch device, cpu or cuda")
    args = parser.parse_args(argv)
    try:
        record = train(
            args.samples,
            args.out,
            seed=args.seed,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            batch=args.batch,
            hidden=args.hidden,
            layers=args.layers,
            device=args.device,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"decoder-train: {error}", file=sys.stderr)
        return 2
    print(
        f"{record.shots} shots, {record.epochs} epochs, held-out accuracy "
        f"{record.held_out_accuracy:.3f} in {record.seconds:.0f} s -> {args.out / RECORD}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
