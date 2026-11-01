import pytest

from sweep.cell import Cell
from sweep.grid import GRID, Grid, expected_cost


def test_grid_runs_its_longest_cells_first() -> None:
    grid = Grid(distances=(3, 5), noise_rates=(0.001, 0.01), shots=10)
    assert [grid.cell(i) for i in range(len(grid))] == [
        Cell(5, 0.01, 10),
        Cell(3, 0.01, 10),
        Cell(5, 0.001, 10),
        Cell(3, 0.001, 10),
    ]


def test_expected_cost_grows_as_the_cube_of_distance_and_with_noise() -> None:
    assert expected_cost(Cell(11, 0.001, 10)) < expected_cost(Cell(9, 0.02, 10))
    assert expected_cost(Cell(9, 0.01, 10)) == pytest.approx(27 * expected_cost(Cell(3, 0.01, 10)))


def test_the_sweep_grid_never_gets_longer_along_its_index() -> None:
    costs = [expected_cost(GRID.cell(i)) for i in range(len(GRID))]
    assert costs == sorted(costs, reverse=True)
    assert GRID.cell(0) == Cell(11, 0.02, 100_000)
    assert GRID.cell(len(GRID) - 1) == Cell(3, 0.001, 100_000)


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
