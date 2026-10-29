"""Sampling and decoding of one cell: Stim samples, PyMatching decodes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from math import sqrt

import numpy as np
import pymatching
import stim

from sweep.cell import Cell

Z_95 = 1.96


@dataclass(frozen=True)
class CellResult:
    """What decoding one cell produced.

    Attributes:
        cell: The cell that was decoded.
        errors: Shots whose decoded correction disagreed with the true logical observable.
        seconds: Wall-clock time of sampling plus decoding.
        seed: Sampler seed, kept so the result can be reproduced bit for bit.
    """

    cell: Cell
    errors: int
    seconds: float
    seed: int

    @property
    def logical_error_rate(self) -> float:
        """Fraction of shots that ended in a logical error."""
        return self.errors / self.cell.shots

    @property
    def interval(self) -> tuple[float, float]:
        """95% Wilson score interval around the logical error rate."""
        return wilson_interval(self.errors, self.cell.shots)


def wilson_interval(errors: int, shots: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a proportion, well behaved at zero and at small counts.

    Args:
        errors: Successes counted, here logical errors.
        shots: Trials.
        z: Standard-normal quantile for the confidence level; 1.96 gives 95%.

    Returns:
        The lower and upper bounds, clamped to [0, 1].
    """
    rate = errors / shots
    denominator = 1 + z**2 / shots
    centre = (rate + z**2 / (2 * shots)) / denominator
    spread = z * sqrt(rate * (1 - rate) / shots + z**2 / (4 * shots**2)) / denominator
    low = 0.0 if errors == 0 else centre - spread
    high = 1.0 if errors == shots else centre + spread
    return low, high


def decode(cell: Cell, seed: int = 0) -> CellResult:
    """Sample a cell's syndromes with Stim and decode them with PyMatching.

    The circuit is Stim's rotated memory-Z surface code with as many rounds as
    the distance and the cell's noise rate on every channel. Samples are kept
    bit-packed so a large cell stays under a byte per detector-shot.

    Args:
        cell: What to simulate.
        seed: Sampler seed; the same seed gives the same result.

    Returns:
        The error count with its timing, from which the rate and interval follow.
    """
    start = time.perf_counter()
    circuit = stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=cell.distance,
        rounds=cell.distance,
        after_clifford_depolarization=cell.noise,
        before_round_data_depolarization=cell.noise,
        before_measure_flip_probability=cell.noise,
        after_reset_flip_probability=cell.noise,
    )
    syndromes, observables = circuit.compile_detector_sampler(seed=seed).sample(
        cell.shots, separate_observables=True, bit_packed=True
    )
    model = circuit.detector_error_model(decompose_errors=True)
    predictions = pymatching.Matching.from_detector_error_model(model).decode_batch(
        syndromes, bit_packed_shots=True, bit_packed_predictions=True
    )
    errors = int(np.any(predictions != observables, axis=1).sum())
    return CellResult(cell=cell, errors=errors, seconds=time.perf_counter() - start, seed=seed)
