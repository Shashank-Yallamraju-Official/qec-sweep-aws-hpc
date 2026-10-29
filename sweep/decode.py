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
    cell: Cell
    errors: int
    seconds: float
    seed: int

    @property
    def logical_error_rate(self) -> float:
        return self.errors / self.cell.shots

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.errors, self.cell.shots)


def wilson_interval(errors: int, shots: int, z: float = Z_95) -> tuple[float, float]:
    rate = errors / shots
    denominator = 1 + z**2 / shots
    centre = (rate + z**2 / (2 * shots)) / denominator
    spread = z * sqrt(rate * (1 - rate) / shots + z**2 / (4 * shots**2)) / denominator
    low = 0.0 if errors == 0 else centre - spread
    high = 1.0 if errors == shots else centre + spread
    return low, high


def decode(cell: Cell, seed: int = 0) -> CellResult:
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
