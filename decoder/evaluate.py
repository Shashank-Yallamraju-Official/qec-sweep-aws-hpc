"""One cell decoded by the trained model, as a result the sweep can write and compare.

The cell is sampled exactly as its training set was, round by round under the
chosen noise model, and the model's call on every shot is checked against the
observable. What comes back is the sweep's ``CellResult`` with ``learned`` as its
decoder, so the reducer, the plot and the comparison treat it like any other cell.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch

from decoder.model import RecurrentDecoder, load
from decoder.sample import Noise, layout, noisy_circuit, sample
from sweep.cell import Cell
from sweep.decode import CellResult

LEARNED = "learned"
BATCH = 4096


def decode(
    cell: Cell, model: Path, seed: int = 0, noise: Noise = "depolarising", batch: int = BATCH
) -> CellResult:
    """Sample a cell's syndromes and decode them with a saved model.

    Args:
        cell: What to simulate.
        model: A ``decoder.pt`` written by training, for a code of this cell's distance.
        seed: Sampler seed; the same seed gives the same shots.
        noise: The noise model the shots are drawn under.
        batch: Shots the model sees per forward pass, so a large cell fits in memory.

    Returns:
        The error count with its timing, decoder ``learned``.

    Raises:
        ValueError: When the model was trained for a code of another distance.
    """
    started = datetime.now(UTC)
    start = time.perf_counter()
    decoder = fit_for(load(model), cell, noise)
    samples = sample(cell, seed=seed, noise=noise)
    detectors = torch.from_numpy(samples.detectors)
    called = [decoder.predict(part).numpy() for part in torch.split(detectors, batch)]
    errors = int(np.sum(np.concatenate(called) != samples.flips))
    return CellResult(
        cell=cell,
        errors=errors,
        seconds=time.perf_counter() - start,
        seed=seed,
        started=started,
        decoder=LEARNED,
    )


def fit_for(decoder: RecurrentDecoder, cell: Cell, noise: Noise) -> RecurrentDecoder:
    """The model, once its input width matches the cell's code.

    Raises:
        ValueError: When the stabiliser counts differ, which is a model of another distance.
    """
    stabilisers = layout(noisy_circuit(cell, noise)).stabilisers
    if decoder.stabilisers != stabilisers:
        msg = (
            f"the model reads {decoder.stabilisers} stabilisers a round, a code of another "
            f"distance; distance {cell.distance} has {stabilisers}"
        )
        raise ValueError(msg)
    return decoder
