import pytest

from sweep.cell import Cell


def test_name_formats_noise_compactly() -> None:
    assert Cell(distance=5, noise=1e-3, shots=100_000).name == "d5_p0.001_s100000"


def test_rejects_even_distance() -> None:
    with pytest.raises(ValueError, match="odd"):
        Cell(distance=4, noise=0.01, shots=10)


def test_rejects_distance_below_three() -> None:
    with pytest.raises(ValueError, match="3"):
        Cell(distance=1, noise=0.01, shots=10)


@pytest.mark.parametrize("noise", [0.0, 1.0, -0.1])
def test_rejects_noise_outside_unit_interval(noise: float) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        Cell(distance=3, noise=noise, shots=10)


def test_rejects_non_positive_shots() -> None:
    with pytest.raises(ValueError, match="positive"):
        Cell(distance=3, noise=0.01, shots=0)


def test_name_distinguishes_close_noise_rates() -> None:
    close = Cell(distance=5, noise=0.00126896, shots=10).name
    closer = Cell(distance=5, noise=0.001268961, shots=10).name
    assert close != closer
