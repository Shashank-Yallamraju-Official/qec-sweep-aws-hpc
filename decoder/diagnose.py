"""Where a chained run left the learned decoder: the ``decoder-diagnose`` command.

An experiment's first step is to say where things stand, and to say it from
records rather than from numbers typed in. Given one chain, this reads its training
records and its two evaluations and answers three questions per cell and per
training: how far the learned decoder is from matching and from the floor, the
decoder that always says no flip; whether the training was still improving when it
stopped, read from the held-out curve it stops on, and whether its held-out accuracy
trails its training accuracy; and whether each evaluated cell lies at a noise rate
the model trained on at all. The floor is the one number no record carries, so it
is resampled from the cell's circuit with the seed and noise model its evaluation
row names.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import pyarrow as pa

from results.compare import CellComparison, Side, compare
from results.run import read_cells
from results.store import locate
from sweep.cell import Cell
from sweep.noise import NOISE_MODELS, Noise, noisy_circuit

TRAINING_RECORD = "train.json"
FLOOR_SHOTS = 100_000
"""Shots the floor is estimated from: enough for three figures, bounded for a large cell."""
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

    The curve judged is the held-out loss where the record has one, since training
    stops on it; a record from before early stopping is judged on its training loss.

    Attributes:
        key: The training run's address.
        cell: The cell it trained on.
        epochs: Passes it made over the training shots.
        max_epochs: Passes it was allowed; equal to ``epochs`` without early stopping.
        losses: The curve judged, one value per epoch.
        best_epoch: The epoch, counted from one, with the lowest value on that curve.
        accuracy: Fraction of training shots called right at the end.
        held_out_accuracy: Fraction of held-out shots called right.
    """

    key: str
    cell: Cell
    epochs: int
    max_epochs: int
    losses: tuple[float, ...]
    best_epoch: int
    accuracy: float
    held_out_accuracy: float

    @property
    def last_loss(self) -> float:
        """The curve's value after the last epoch."""
        return self.losses[-1]

    @property
    def last_epoch_drop(self) -> float:
        """The fraction the curve fell by over the last epoch; zero when it could not."""
        if len(self.losses) <= 1 or self.losses[-2] == 0:
            return 0.0
        return (self.losses[-2] - self.losses[-1]) / self.losses[-2]

    @property
    def stopped_early(self) -> bool:
        """Whether patience ended the training before its cap."""
        return self.epochs < self.max_epochs

    @property
    def still_improving(self) -> bool:
        """Whether more epochs would have gone on lowering the curve."""
        return not self.stopped_early and self.last_epoch_drop > STILL_IMPROVING

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
        comparison: Matching against the learned decoder on this cell, as the comparison
            tool judges it; its ``a`` is matching and its ``b`` the learned decoder.
        floor: The error rate of the decoder that always says no flip.
        in_distribution: Whether the model trained at this cell's noise rate.
    """

    comparison: CellComparison
    floor: float
    in_distribution: bool

    @property
    def cell(self) -> Cell:
        """The cell evaluated."""
        return self.comparison.cell

    @property
    def matching(self) -> Side:
        """Matching's count and interval."""
        return self.comparison.a

    @property
    def learned(self) -> Side:
        """The learned decoder's count and interval."""
        return self.comparison.b

    @property
    def ratio(self) -> float | None:
        """Learned over matching; undefined when matching saw no error."""
        return self.comparison.ratio

    @property
    def verdict(self) -> str:
        """``lower``, ``higher`` or ``within``, as the comparison calls it."""
        return self.comparison.verdict


@dataclass(frozen=True)
class Diagnosis:
    """What one chain says about the learned decoder.

    Attributes:
        chain: The chain's address.
        noise: The noise model every run in it used.
        trained_at: The noise rates the models trained at.
        trainings: One per training run, in the chain's order.
        cells: One per cell both evaluations decoded, by distance then noise rate.
        unmatched: Cells one evaluation decoded and the other did not, by name.
        read: Every address this diagnosis was read from.
    """

    chain: str
    noise: Noise
    trained_at: tuple[float, ...]
    trainings: tuple[Training, ...]
    cells: tuple[CellState, ...]
    unmatched: tuple[str, ...]
    read: tuple[str, ...]


def diagnose(chain: str) -> Diagnosis:
    """Read a chain's records and its two evaluations into a diagnosis.

    Args:
        chain: ``s3://bucket/chains/<run>`` or a directory laid out the same way.

    The floor of each cell is resampled with the seed and noise model the evaluation's
    own row records, so it is the stream the decoders were judged on.

    Raises:
        KeyError: When the chain's record lacks the children a chain writes.
        ValueError: When an evaluated cell names a noise model the sweep does not have.
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
    sampled = _sampling(matching[1])
    cells = tuple(
        CellState(
            comparison=c,
            floor=_floor(c.cell, *sampled[c.cell]),
            in_distribution=c.cell.noise in trained_at,
        )
        for c in comparison.cells
    )
    both = {c.cell for c in comparison.cells}
    unmatched = tuple(
        sorted(
            {Cell(*k).name for k in _cell_keys(matching[1]) | _cell_keys(learned[1])}
            - {c.name for c in both}
        )
    )
    return Diagnosis(
        chain=store.uri(key),
        noise=noise,
        trained_at=trained_at,
        trainings=trainings,
        cells=cells,
        unmatched=unmatched,
        read=(store.uri(key), *(t.key for t in trainings), matching[0], learned[0]),
    )


def _cell_keys(table: pa.Table) -> set[tuple[int, float, int]]:
    return {
        (int(r["distance"]), float(r["noise"]), int(r["shots"]))
        for r in table.select(["distance", "noise", "shots"]).to_pylist()
    }


def _sampling(table: pa.Table) -> dict[Cell, tuple[Noise, int]]:
    out: dict[Cell, tuple[Noise, int]] = {}
    for r in table.to_pylist():
        model = str(r.get("noise_model", "depolarising"))
        if model not in NOISE_MODELS:
            msg = f"cell d{r['distance']} p{r['noise']} names an unknown noise model {model}"
            raise ValueError(msg)
        noise: Noise = "correlated" if model == "correlated" else "depolarising"
        out[Cell(int(r["distance"]), float(r["noise"]), int(r["shots"]))] = (noise, int(r["seed"]))
    return out


def _training(address: str) -> Training:
    store, key = locate(address)
    raw: dict[str, Any] = json.loads(store.read(f"{key}/{TRAINING_RECORD}").decode())
    losses = tuple(float(x) for x in raw.get("held_out_losses") or raw["epoch_losses"])
    cell = raw["cell"]
    return Training(
        key=store.uri(key),
        cell=Cell(int(cell["distance"]), float(cell["noise"]), int(cell["shots"])),
        epochs=int(raw["epochs"]),
        max_epochs=int(raw.get("max_epochs", raw["epochs"])),
        losses=losses,
        best_epoch=losses.index(min(losses)) + 1,
        accuracy=float(raw["accuracy"]),
        held_out_accuracy=float(raw["held_out_accuracy"]),
    )


def _evaluation(address: str) -> tuple[str, Any]:
    store, key = locate(address)
    return store.uri(key), read_cells(store, key)


def _floor(cell: Cell, noise: Noise, seed: int) -> float:
    sampler = noisy_circuit(cell, noise).compile_detector_sampler(seed=seed)
    _, observables = sampler.sample(min(cell.shots, FLOOR_SHOTS), separate_observables=True)
    return float(observables[:, 0].mean())


def report(diagnosis: Diagnosis) -> str:
    """The diagnosis as Markdown an experiment record can carry as its State."""
    lines = [
        f"Chain {diagnosis.chain}, {diagnosis.noise} noise, trained at "
        + ", ".join(f"p = {p}" for p in diagnosis.trained_at),
        "",
        (
            "| training | epochs | best epoch | last loss | drop over last epoch | train acc | "
            "held-out acc | fit |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        *(
            f"| {t.cell.name} | {t.epochs} of {t.max_epochs} | {t.best_epoch} | "
            f"{t.last_loss:.4f} | {t.last_epoch_drop:.1%} | {t.accuracy:.4f} | "
            f"{t.held_out_accuracy:.4f} | {t.fit} |"
            for t in diagnosis.trainings
        ),
        "",
        (
            f"| cell | floor (from {FLOOR_SHOTS:,} shots at most) | matching | learned | "
            "learned / matching | verdict | distribution |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- |",
        *(
            f"| {c.cell.name} | {c.floor:.4f} | {c.matching.rate:.5f} | {c.learned.rate:.5f} | "
            f"{'-' if c.ratio is None else f'{c.ratio:.2f}'} | {c.verdict} | "
            f"{'on' if c.in_distribution else 'off'} |"
            for c in diagnosis.cells
        ),
        *(
            [
                "",
                "Decoded by one evaluation only, so missing above: "
                + ", ".join(diagnosis.unmatched),
            ]
            if diagnosis.unmatched
            else []
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
