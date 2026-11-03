"""Trains the recurrent decoder on a generate run's samples: the ``decoder-train`` command.

One call reads every ``.npz`` a generate run wrote for one cell, holds a tenth of
the shots back, fits the model by mini-batched Adam on the binary cross-entropy of
the observable flip, saves the model and writes a ``train.json`` beside it that
says what was trained on what, how well it did on the held-out shots, and where
and how long it ran. The device is a parameter so the same call moves to a GPU
queue the day one exists.

Launched once per node with ``RANK``, ``WORLD_SIZE``, ``MASTER_ADDR`` and
``MASTER_PORT`` set, the ranks train one model between them: each holds a share of
the training shots and the gradients are averaged every step, so the result is one
model trained on every shot, in less wall-clock time.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
import torch.distributed as dist
from torch import Tensor, nn
from torch.nn.parallel import DistributedDataParallel

from decoder.model import HIDDEN, LAYERS, RecurrentDecoder, build, save
from decoder.sample import read
from sweep.cell import Cell

MODEL = "decoder.pt"
RECORD = "train.json"
HELD_OUT = 0.1
BACKENDS = {"cpu": "gloo", "cuda": "nccl"}


@dataclass(frozen=True)
class World:
    """The ranks one training is spread over, as the launcher's environment names them.

    Attributes:
        rank: This process's place among the ranks, counted from zero.
        size: How many ranks share the training; one when it runs alone.
    """

    rank: int = 0
    size: int = 1

    @classmethod
    def from_environment(cls) -> World:
        """The world ``RANK`` and ``WORLD_SIZE`` describe; alone when they are unset."""
        return cls(
            rank=int(os.environ.get("RANK", "0")), size=int(os.environ.get("WORLD_SIZE", "1"))
        )

    @property
    def leader(self) -> bool:
        """Whether this rank writes the model and the record."""
        return self.rank == 0

    @property
    def shared(self) -> bool:
        """Whether more than one rank is training."""
        return self.size > 1


ALONE = World()


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
        batch: Shots per step, on each rank.
        ranks: Processes the training was spread over.
        epoch_losses: Mean training loss after each epoch, over every rank's shots.
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
    ranks: int
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


def score(
    model: RecurrentDecoder, detectors: Tensor, flips: Tensor, world: World = ALONE
) -> tuple[float, float]:
    """Mean loss and accuracy of the model on a set, without tracking gradients.

    With several ranks each scores its own shots and the means are taken over all of them.
    """
    model.eval()
    with torch.no_grad():
        logits = model(detectors)
        loss = nn.functional.binary_cross_entropy_with_logits(
            logits, flips.to(torch.float32), reduction="sum"
        )
        right = ((logits > 0).to(torch.uint8) == flips).to(torch.float32).sum()
    sums = torch.tensor([float(loss), float(right), float(len(flips))])
    if world.shared:
        dist.all_reduce(sums)
    return float(sums[0] / sums[2]), float(sums[1] / sums[2])


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
    world: World | None = None,
) -> Training:
    """Train a decoder on a directory of samples, save it and its record under ``out_dir``.

    The seed fixes everything that could differ between two runs on one machine:
    which shots are held out, the initial weights and the order of the batches.
    With several ranks each takes every ``size``-th training shot; the model and
    record are written by rank zero, and every rank returns the same record.
    """
    started = time.perf_counter()
    world = world or World.from_environment()
    cell, names, detectors, flips = load_samples(samples_dir)
    where = torch.device(device)
    (train_x, train_y), (held_x, held_y) = _split(detectors.to(where), flips.to(where), seed, world)
    torch.manual_seed(seed)
    model = build(cell, hidden=hidden, layers=layers).to(where)
    if world.shared:
        dist.init_process_group(BACKENDS[where.type], rank=world.rank, world_size=world.size)
    settings = Settings(seed, epochs, learning_rate, batch)
    epoch_losses = _fit(model, train_x, train_y, settings, world)
    loss, accuracy = score(model, train_x, train_y, world)
    held_loss, held_accuracy = score(model, held_x, held_y)
    record = Training(
        cell=cell,
        samples=names,
        shots=len(flips),
        held_out=len(held_y),
        seed=seed,
        epochs=epochs,
        learning_rate=learning_rate,
        batch=batch,
        ranks=world.size,
        epoch_losses=tuple(epoch_losses),
        loss=loss,
        accuracy=accuracy,
        held_out_loss=held_loss,
        held_out_accuracy=held_accuracy,
        device=device,
        seconds=time.perf_counter() - started,
        torch=torch.__version__,
    )
    if world.leader:
        out_dir.mkdir(parents=True, exist_ok=True)
        save(model.to("cpu"), out_dir / MODEL)
        (out_dir / RECORD).write_text(json.dumps(asdict(record), indent=2))
    if world.shared:
        dist.barrier()
        dist.destroy_process_group()
    return record


@dataclass(frozen=True)
class Settings:
    """How the fit is run: the seed, the passes, the step size and the batch."""

    seed: int
    epochs: int
    learning_rate: float
    batch: int


Split = tuple[tuple[Tensor, Tensor], tuple[Tensor, Tensor]]
"""This rank's training detectors and flips, then the held-out ones every rank shares."""


def _split(detectors: Tensor, flips: Tensor, seed: int, world: World) -> Split:
    order = torch.randperm(len(flips), generator=torch.Generator().manual_seed(seed))
    held = round(len(flips) * HELD_OUT)
    held_idx, share = order[:held], order[held:][world.rank :: world.size]
    return (detectors[share], flips[share]), (detectors[held_idx], flips[held_idx])


def _fit(
    model: RecurrentDecoder, train_x: Tensor, train_y: Tensor, settings: Settings, world: World
) -> list[float]:
    trainee: nn.Module = DistributedDataParallel(model) if world.shared else model
    optimiser = torch.optim.Adam(trainee.parameters(), lr=settings.learning_rate)
    # Each rank shuffles its own share in its own order; the split is already shared.
    shuffler = torch.Generator().manual_seed(settings.seed * world.size + world.rank)
    epoch_losses = []
    for _ in range(settings.epochs):
        trainee.train()
        sums = torch.zeros(2)
        for rows in torch.split(torch.randperm(len(train_y), generator=shuffler), settings.batch):
            optimiser.zero_grad()
            step_loss = nn.functional.binary_cross_entropy_with_logits(
                trainee(train_x[rows]), train_y[rows].to(torch.float32)
            )
            step_loss.backward()  # type: ignore[no-untyped-call]
            optimiser.step()
            sums += torch.tensor([step_loss.detach().item() * len(rows), float(len(rows))])
        if world.shared:
            dist.all_reduce(sums)
        epoch_losses.append(float(sums[0] / sums[1]))
    return epoch_losses


def main(argv: Sequence[str] | None = None) -> int:
    """Train from the command line and print where the record went.

    Args:
        argv: ``--samples dir --out dir [--seed] [--epochs] [--learning-rate] [--batch]
            [--hidden] [--layers] [--device]``; ``None`` reads ``sys.argv``. The world
            comes from ``RANK`` and ``WORLD_SIZE`` in the environment.

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
    parser.add_argument("--batch", type=int, default=256, help="shots per step, per rank")
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
        f"{record.shots} shots, {record.epochs} epochs on {record.ranks} rank(s), held-out "
        f"accuracy {record.held_out_accuracy:.3f} in {record.seconds:.0f} s -> {args.out / RECORD}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
