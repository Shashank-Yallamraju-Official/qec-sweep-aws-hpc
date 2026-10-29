"""The sweep grid, and the mapping from a job-array index to one of its cells."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sweep.cell import Cell


@dataclass(frozen=True)
class Grid:
    """Every (distance, noise rate) pair at one shot count, in a fixed order.

    Attributes:
        distances: Code distances, each odd.
        noise_rates: Physical error rates, ascending.
        shots: Shots per cell.
    """

    distances: tuple[int, ...]
    noise_rates: tuple[float, ...]
    shots: int

    def __len__(self) -> int:
        return len(self.distances) * len(self.noise_rates)

    def cell(self, index: int) -> Cell:
        """The cell at an array index: distances vary fastest, noise rates slowest.

        Raises:
            IndexError: When the index is past the end of the grid.
        """
        if not 0 <= index < len(self):
            msg = f"index {index} is outside a grid of {len(self)} cells"
            raise IndexError(msg)
        rate, distance = divmod(index, len(self.distances))
        return Cell(self.distances[distance], self.noise_rates[rate], self.shots)


def _log_spaced(low: float, high: float, count: int) -> tuple[float, ...]:
    # Five significant figures keep file names short and the endpoints exact.
    return tuple(float(f"{p:.5g}") for p in np.geomspace(low, high, count))


GRID = Grid(distances=(3, 5, 7, 9, 11), noise_rates=_log_spaced(1e-3, 2e-2, 40), shots=100_000)
