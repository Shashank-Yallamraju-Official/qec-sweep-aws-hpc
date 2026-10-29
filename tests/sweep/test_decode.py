from sweep.cell import Cell
from sweep.decode import decode, wilson_interval


def test_wilson_interval_brackets_the_rate() -> None:
    low, high = wilson_interval(errors=10, shots=1000)
    assert low < 0.01 < high


def test_wilson_interval_with_zero_errors() -> None:
    low, high = wilson_interval(errors=0, shots=1000)
    assert low == 0
    assert high > 0


def test_decode_is_deterministic_for_a_seed() -> None:
    cell = Cell(distance=3, noise=0.01, shots=1000)
    assert decode(cell, seed=7).errors == decode(cell, seed=7).errors


def test_decode_counts_fewer_errors_at_larger_distance() -> None:
    small = decode(Cell(distance=3, noise=0.005, shots=2000))
    large = decode(Cell(distance=5, noise=0.005, shots=2000))
    assert large.errors < small.errors


def test_decode_result_carries_rate_interval_and_timing() -> None:
    cell = Cell(distance=3, noise=0.01, shots=1000)
    result = decode(cell, seed=1)
    low, high = result.interval
    assert result.cell == cell
    assert result.logical_error_rate == result.errors / cell.shots
    assert low <= result.logical_error_rate <= high
    assert result.seconds > 0
    assert result.seed == 1
