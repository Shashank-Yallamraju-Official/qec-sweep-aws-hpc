"""Where a chained run left the learned decoder: the ``decoder-diagnose`` command.

An experiment's first step is to say where things stand, and to say it from
records rather than from numbers typed in. Given one chain, this reads its training
records and its two evaluations and answers three questions per cell and per
training: how far the learned decoder is from matching and from the floor, the
decoder that always says no flip; whether the training was still improving when it
stopped, and whether its held-out accuracy trails its training accuracy; and whether
each evaluated cell lies at a noise rate the model trained on at all. The floor is
the one number no record carries, so it is resampled from the cell's circuit by the
cell's seed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from results.compare import CellComparison, Side, compare
from results.run import read_cells
from results.store import locate
from sweep.cell import Cell
from sweep.noise import Noise, noisy_circuit

TRAINING_RECORD = "train.json"
STILL_IMPROVING = 0.01
"""A loss that fell by more than this fraction over the last epoch was still falling."""
HELD_OUT_GAP = 0.01
"""Training accuracy more than this above held-out accuracy is memorising, not learning."""

Fit = Literal["underfit", "overfit", "converged"]
UNDERFIT: Fit = "underfit"
OVERFIT: Fit = "overfit"
CONVERGED: Fit = "converged"


@dataclass(frozen=True)
class Training:
    """One training run, read for whether it had finished learning.

    Attributes:
        key: The training run's address.
        cell: The cell it trained on.
        epochs: Passes it made over the training shots.
        last_loss: Mean training loss after the last epoch.
        last_epoch_drop: The fraction the loss fell by over the last epoch.
        accuracy: Fraction of training shots called right at the end.
        held_out_accuracy: Fraction of held-out shots called right.
    """

    key: str
    cell: Cell
    epochs: int
    last_loss: float
    last_epoch_drop: float
    accuracy: float
    held_out_accuracy: float

    @property
    def still_improving(self) -> bool:
        """Whether more epochs would have gone on lowering the loss."""
        return self.last_epoch_drop > STILL_IMPROVING

    @property
    def fit(self) -> Fit:
        """Overfit when held-out trails training; underfit when still improving; else converged."""
        if self.accuracy - self.held_out_accuracy > HELD_OUT_GAP:
            return OVERFIT
        return UNDERFIT if self.still_improving else CONVERGED


@dataclass(frozen=True)
class CellState:
    """One evaluated cell: the floor, both decoders and whether the model had seen its rate.

    Attributes:
        cell: The cell evaluated.
        floor: The error rate of the decoder that always says no flip.
        matching: Matching's count and interval.
        learned: The learned decoder's count and interval.
        in_distribution: Whether the model trained at this cell's noise rate.
    """

    cell: Cell
    floor: float
    matching: Side
    learned: Side
    in_distribution: bool

    @property
    def ratio(self) -> float | None:
        """Learned over matching; undefined when matching saw no error."""
        return None if self.matching.errors == 0 else self.learned.rate / self.matching.rate

    @property
    def verdict(self) -> str:
        """``lower``, ``higher`` or ``within``, as the comparison calls it."""
        return CellComparison(self.cell, self.matching, self.learned).verdict


@dataclass(frozen=True)
class Diagnosis:
    """What one chain says about the learned decoder.

    Attributes:
        chain: The chain's address.
        noise: The noise model every run in it used.
        trained_at: The noise rates the models trained at.
        trainings: One per training run, in the chain's order.
        cells: One per evaluated cell, by distance then noise rate.
        read: Every address this diagnosis was read from.
    """

    chain: str
    noise: Noise
    trained_at: tuple[float, ...]
    trainings: tuple[Training, ...]
    cells: tuple[CellState, ...]
    read: tuple[str, ...]


def diagnose(chain: str) -> Diagnosis:
    """Read a chain's records and its two evaluations into a diagnosis.

    Args:
        chain: ``s3://bucket/chains/<run>`` or a directory laid out the same way.

    Raises:
        KeyError: When the chain's record lacks the children a chain writes.
    """
    store, key = locate(chain)
    record = json.loads(store.read(f"{key}/run.json").decode())
    noise: Noise = "correlated" if record["noise"] == "correlated" else "depolarising"
    children = record["children"]
    trainings = tuple(_training(address) for address in children["train"])
    trained_at = tuple(sorted({t.cell.noise for t in trainings}))
    matching, learned = (
        _evaluation(children["evaluations"][decoder]) for decoder in ("pymatching", "learned")
    )
    comparison = compare(matching[1], learned[1])
    cells = tuple(
        CellState(
            cell=c.cell,
            floor=_floor(c.cell, noise, int(record.get("seed", 0))),
            matching=c.a,
            learned=c.b,
            in_distribution=c.cell.noise in trained_at,
        )
        for c in comparison.cells
    )
    return Diagnosis(
        chain=store.uri(key),
        noise=noise,
        trained_at=trained_at,
        trainings=trainings,
        cells=cells,
        read=(store.uri(key), *(t.key for t in trainings), matching[0], learned[0]),
    )


def _training(address: str) -> Training:
    store, key = locate(address)
    raw: dict[str, Any] = json.loads(store.read(f"{key}/{TRAINING_RECORD}").decode())
    losses = raw["epoch_losses"]
    drop = (losses[-2] - losses[-1]) / losses[-2] if len(losses) > 1 else 0.0
    cell = raw["cell"]
    return Training(
        key=store.uri(key),
        cell=Cell(int(cell["distance"]), float(cell["noise"]), int(cell["shots"])),
        epochs=int(raw["epochs"]),
        last_loss=float(losses[-1]),
        last_epoch_drop=drop,
        accuracy=float(raw["accuracy"]),
        held_out_accuracy=float(raw["held_out_accuracy"]),
    )


def _evaluation(address: str) -> tuple[str, Any]:
    store, key = locate(address)
    return store.uri(key), read_cells(store, key)


def _floor(cell: Cell, noise: Noise, seed: int) -> float:
    sampler = noisy_circuit(cell, noise).compile_detector_sampler(seed=seed)
    _, observables = sampler.sample(cell.shots, separate_observables=True)
    return float(observables[:, 0].mean())


def report(diagnosis: Diagnosis) -> str:
    """The diagnosis as Markdown an experiment record can carry as its State."""
    lines = [
        f"Chain {diagnosis.chain}, {diagnosis.noise} noise, trained at "
        + ", ".join(f"p = {p}" for p in diagnosis.trained_at),
        "",
        "| training | epochs | last loss | drop over last epoch | train acc | held-out acc | fit |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *(
            f"| {t.cell.name} | {t.epochs} | {t.last_loss:.4f} | {t.last_epoch_drop:.1%} | "
            f"{t.accuracy:.4f} | {t.held_out_accuracy:.4f} | {t.fit} |"
            for t in diagnosis.trainings
        ),
        "",
        "| cell | floor | matching | learned | learned / matching | verdict | distribution |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *(
            f"| {c.cell.name} | {c.floor:.4f} | {c.matching.rate:.5f} | {c.learned.rate:.5f} | "
            f"{'-' if c.ratio is None else f'{c.ratio:.2f}'} | {c.verdict} | "
            f"{'on' if c.in_distribution else 'off'} |"
            for c in diagnosis.cells
        ),
        "",
        "Read: " + ", ".join(diagnosis.read),
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Diagnose one chain from the command line and print the report.

    Args:
        argv: ``<chain>``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when the chain cannot be read as one.
    """
    parser = argparse.ArgumentParser(
        prog="decoder-diagnose", description="where a chained run left the learned decoder"
    )
    parser.add_argument("chain", help="s3://bucket/chains/<run> or a directory laid out so")
    args = parser.parse_args(argv)
    try:
        print(report(diagnose(args.chain)), end="")
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"decoder-diagnose: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
