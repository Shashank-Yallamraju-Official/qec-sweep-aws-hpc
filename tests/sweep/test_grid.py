import pytest
from sweep.grid import GRID, Grid

from sweep.cell import Cell


def test_grid_enumerates_every_distance_for_each_noise_rate() -> None:
    grid = Grid(distances=(3, 5), noise_rates=(0.001, 0.01), shots=10)
    assert [grid.cell(i) for i in range(len(grid))] == [
        Cell(3, 0.001, 10),
        Cell(5, 0.001, 10),
        Cell(3, 0.01, 10),
        Cell(5, 0.01, 10),
    ]


def test_grid_rejects_an_index_past_the_end() -> None:
    grid = Grid(distances=(3,), noise_rates=(0.001,), shots=10)
    with pytest.raises(IndexError, match="1 cell"):
        grid.cell(1)


def test_the_sweep_grid_has_hundreds_of_cells_over_a_decade_of_noise() -> None:
    assert len(GRID) == 200
    assert GRID.distances == (3, 5, 7, 9, 11)
    assert GRID.noise_rates[0] == 0.001
    assert GRID.noise_rates[-1] == 0.02
    assert all(GRID.cell(i).shots == 100_000 for i in range(len(GRID)))
