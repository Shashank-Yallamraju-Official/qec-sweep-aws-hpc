"""The sweep grid, and the mapping from a job-array index to one of its cells."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np

from sweep.cell import Cell


def expected_cost(cell: Cell) -> float:
    """How long a cell takes to decode, up to a constant, from its distance and noise.

    Matching works on a graph of about distance cubed detectors, with a fraction of
    them lit that grows with the noise rate; one node's run bore this out.
    """
    return cell.distance**3 * cell.noise


@dataclass(frozen=True)
class Grid:
    """Every (distance, noise rate) pair at one shot count, longest cells first.

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

    @cached_property
    def cells(self) -> tuple[Cell, ...]:
        """Every cell, by falling expected cost, so an array's slow tasks start first."""
        pairs = ((d, p) for p in self.noise_rates for d in self.distances)
        cells = (Cell(d, p, self.shots) for d, p in pairs)
        return tuple(sorted(cells, key=expected_cost, reverse=True))

    def cell(self, index: int) -> Cell:
        """The cell an array task with this index decodes.

        Raises:
            IndexError: When the index is past the end of the grid.
        """
        if not 0 <= index < len(self):
            msg = f"index {index} is outside a grid of {len(self)} cells"
            raise IndexError(msg)
        return self.cells[index]


def _log_spaced(low: float, high: float, count: int) -> tuple[float, ...]:
    # Five significant figures keep file names short and the endpoints exact.
    return tuple(float(f"{p:.5g}") for p in np.geomspace(low, high, count))


GRID = Grid(distances=(3, 5, 7, 9, 11), noise_rates=_log_spaced(1e-3, 2e-2, 40), shots=100_000)
