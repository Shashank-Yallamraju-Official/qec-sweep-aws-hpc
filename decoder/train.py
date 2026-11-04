"""Trains the recurrent decoder on a generate run's samples: the ``decoder-train`` command.

One call reads every ``.npz`` a generate run wrote for one cell, holds a tenth of
the shots back, fits the model by mini-batched Adam on the binary cross-entropy of
the observable flip, saves the model and writes a ``train.json`` beside it that
says what was trained on what, how well it did on the held-out shots, and where
and how long it ran. Given a patience, the held-out loss is scored after every
epoch and training stops once it has not improved for that many epochs, keeping
the weights of the best epoch; the epoch count is then a cap. The device is a
parameter so the same call moves to a GPU queue the day one exists.

Launched once per node with ``RANK``, ``WORLD_SIZE``, ``MASTER_ADDR`` and
``MASTER_PORT`` set, the ranks train one model between them: each reads only its
share of the sample files, so a set of millions of shots never sits whole in one
node's memory, holds a tenth of its own shots out, and the gradients are averaged
every step, so the result is one model trained on every shot, in less wall-clock time.
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
SCORE_BATCH = 4096
"""Shots scored per forward pass, so a set of millions is scored in bounded memory."""
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
        epochs: Passes made over the training shots.
        max_epochs: The most passes allowed; fewer are made when the held-out loss stalls.
        patience: Epochs without a better held-out loss before stopping; ``None`` never stops early.
        learning_rate: Adam's step size.
        batch: Shots per step, on each rank.
        ranks: Processes the training was spread over.
        epoch_losses: Mean training loss after each epoch, over every rank's shots.
        held_out_losses: Mean held-out loss after each epoch.
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
    max_epochs: int
    patience: int | None
    learning_rate: float
    batch: int
    ranks: int
    epoch_losses: tuple[float, ...]
    held_out_losses: tuple[float, ...]
    loss: float
    accuracy: float
    held_out_loss: float
    held_out_accuracy: float
    device: str
    seconds: float
    torch: str


def load_samples(
    samples_dir: Path, world: World = ALONE
) -> tuple[Cell, tuple[str, ...], Tensor, Tensor]:
    """This rank's share of the sample files under a directory, as detectors and flips.

    The files are shared out round robin by rank, so no rank reads more than it
    trains on; the names returned are every file's, since the record describes the
    whole set.

    Raises:
        FileNotFoundError: When the directory holds no sample file.
        ValueError: When the files were not all sampled from one cell, or there are
            fewer of them than ranks.
    """
    paths = sorted(samples_dir.glob("*.npz"))
    if not paths:
        msg = f"no samples under {samples_dir}"
        raise FileNotFoundError(msg)
    if len(paths) < world.size:
        msg = f"{len(paths)} sample files under {samples_dir} are fewer than {world.size} ranks"
        raise ValueError(msg)
    cells = {_cell_of(p) for p in paths}
    if len(cells) != 1:
        msg = f"the samples under {samples_dir} are not of one cell: {sorted(map(str, cells))}"
        raise ValueError(msg)
    loaded = [read(p) for p in paths[world.rank :: world.size]]
    detectors = torch.from_numpy(np.concatenate([s.detectors for s in loaded]))
    flips = torch.from_numpy(np.concatenate([s.flips for s in loaded]))
    return loaded[0].cell, tuple(p.name for p in paths), detectors, flips


def _cell_of(path: Path) -> Cell:
    # Every rank checks every file's cell, one small array each, before reading its own
    # share: a mixed directory must fail the same way on every rank, not hang in DDP.
    with np.load(path) as data:
        distance, noise_rate, shots = data["cell"]
    return Cell(int(distance), float(noise_rate), int(shots))


def score(
    model: RecurrentDecoder,
    detectors: Tensor,
    flips: Tensor,
    world: World = ALONE,
    batch: int = SCORE_BATCH,
) -> tuple[float, float]:
    """Mean loss and accuracy of the model on a set, without tracking gradients.

    The set is scored a batch at a time, so its size is bounded by the data and not by
    the model's state. With several ranks each scores its own shots and the means are
    taken over all of them.
    """
    model.eval()
    sums = torch.zeros(3, device=detectors.device)
    with torch.no_grad():
        for rows in torch.split(torch.arange(len(flips), device=detectors.device), batch):
            logits = model(detectors[rows])
            target = flips[rows]
            loss = nn.functional.binary_cross_entropy_with_logits(
                logits, target.to(torch.float32), reduction="sum"
            )
            right = ((logits > 0).to(torch.uint8) == target).to(torch.float32).sum()
            sums += torch.tensor([float(loss), float(right), float(len(rows))], device=sums.device)
    if world.shared:
        dist.all_reduce(sums)
    return float(sums[0] / sums[2]), float(sums[1] / sums[2])


def train(  # noqa: PLR0913
    samples_dir: Path,
    out_dir: Path,
    *,
    seed: int = 0,
    epochs: int = 10,
    patience: int | None = None,
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
    ``epochs`` is the number of passes, or with a ``patience`` the most passes: the
    held-out loss is scored after each and training stops, keeping the best epoch's
    weights, once it has gone that many epochs without improving.
    With several ranks each reads its own share of the files and trains on as many
    shots as the rank with the fewest; the model and record are written by rank
    zero, and every rank returns the same record.
    """
    started = time.perf_counter()
    world = world or World.from_environment()
    where = torch.device(device)
    if world.shared:
        dist.init_process_group(BACKENDS[where.type], rank=world.rank, world_size=world.size)
    cell, names, detectors, flips = load_samples(samples_dir, world)
    (train_x, train_y), (held_x, held_y) = split(detectors.to(where), flips.to(where), seed)
    train_x, train_y = _equalise(train_x, train_y, world)
    torch.manual_seed(seed)
    model = build(cell, hidden=hidden, layers=layers).to(where)
    settings = Settings(seed, epochs, patience, learning_rate, batch)
    epoch_losses, held_losses = _fit(model, (train_x, train_y), (held_x, held_y), settings, world)
    loss, accuracy = score(model, train_x, train_y, world)
    held_loss, held_accuracy = score(model, held_x, held_y, world)
    record = Training(
        cell=cell,
        samples=names,
        shots=_total(len(flips), world, where),
        held_out=_total(len(held_y), world, where),
        seed=seed,
        epochs=len(epoch_losses),
        max_epochs=epochs,
        patience=patience,
        learning_rate=learning_rate,
        batch=batch,
        ranks=world.size,
        epoch_losses=tuple(epoch_losses),
        held_out_losses=tuple(held_losses),
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
    """How the fit is run: the seed, the passes, the patience, the step size and the batch."""

    seed: int
    epochs: int
    patience: int | None
    learning_rate: float
    batch: int


Split = tuple[tuple[Tensor, Tensor], tuple[Tensor, Tensor]]
"""This rank's training detectors and flips, then its held-out ones."""


def split(detectors: Tensor, flips: Tensor, seed: int) -> Split:
    """Hold a tenth of the shots out, in an order the seed fixes."""
    order = torch.randperm(len(flips), generator=torch.Generator().manual_seed(seed))
    held = round(len(flips) * HELD_OUT)
    held_idx, training = order[:held], order[held:]
    return (detectors[training], flips[training]), (detectors[held_idx], flips[held_idx])


def _equalise(detectors: Tensor, flips: Tensor, world: World) -> tuple[Tensor, Tensor]:
    # Every rank takes the same number of steps: the ranks average gradients at each
    # step, and one with a step more than the others would wait for it forever.
    if not world.shared:
        return detectors, flips
    count = torch.tensor([len(flips)], device=detectors.device)
    dist.all_reduce(count, op=dist.ReduceOp.MIN)
    return detectors[: int(count)], flips[: int(count)]


def _total(count: int, world: World, where: torch.device) -> int:
    if not world.shared:
        return count
    total = torch.tensor([count], device=where)
    dist.all_reduce(total)
    return int(total)


Set = tuple[Tensor, Tensor]
"""Detectors and the flips that go with them."""


def _fit(
    model: RecurrentDecoder, training: Set, held_out: Set, settings: Settings, world: World
) -> tuple[list[float], list[float]]:
    train_x, train_y = training
    trainee: nn.Module = DistributedDataParallel(model) if world.shared else model
    optimiser = torch.optim.Adam(trainee.parameters(), lr=settings.learning_rate)
    # Each rank shuffles its own share in its own order; the split is already shared.
    shuffler = torch.Generator().manual_seed(settings.seed * world.size + world.rank)
    epoch_losses: list[float] = []
    held_losses: list[float] = []
    best: dict[str, Tensor] = {}
    for _ in range(settings.epochs):
        trainee.train()
        sums = torch.zeros(2, device=train_x.device)
        for rows in torch.split(torch.randperm(len(train_y), generator=shuffler), settings.batch):
            optimiser.zero_grad()
            step_loss = nn.functional.binary_cross_entropy_with_logits(
                trainee(train_x[rows]), train_y[rows].to(torch.float32)
            )
            step_loss.backward()  # type: ignore[no-untyped-call]
            optimiser.step()
            sums += torch.tensor(
                [step_loss.detach().item() * len(rows), float(len(rows))], device=sums.device
            )
        if world.shared:
            dist.all_reduce(sums)
        epoch_losses.append(float(sums[0] / sums[1]))
        # Every rank sees the same mean, so every rank stops on the same epoch.
        held_losses.append(score(model, *held_out, world)[0])
        if settings.patience is None:
            continue
        if held_losses[-1] == min(held_losses):
            best = {k: v.detach().clone() for k, v in model.state_dict().items()}
        elif len(held_losses) - held_losses.index(min(held_losses)) > settings.patience:
            break
    if best:
        model.load_state_dict(best)
    return epoch_losses, held_losses


def main(argv: Sequence[str] | None = None) -> int:
    """Train from the command line and print where the record went.

    Args:
        argv: ``--samples dir --out dir [--seed] [--epochs] [--patience] [--learning-rate]
            [--batch] [--hidden] [--layers] [--device]``; ``None`` reads ``sys.argv``. The world
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
    parser.add_argument(
        "--patience", type=int, help="stop after this many epochs without a better held-out loss"
    )
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
            patience=args.patience,
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
