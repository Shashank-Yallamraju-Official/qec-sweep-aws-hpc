import numpy as np
import pytest

from mpi.gates import Gate, H, T, X


@pytest.mark.parametrize("gate", [H, T, X])
def test_single_qubit_gates_are_unitary(gate: Gate) -> None:
    assert gate.arity == 1
    assert np.allclose(gate.matrix @ gate.matrix.conj().T, np.eye(2))


def test_arity_follows_the_matrix_side() -> None:
    assert Gate("swap", np.eye(4, dtype=np.complex128)).arity == 2


@pytest.mark.parametrize("shape", [(2, 3), (3, 3), (1, 1), (4,)])
def test_a_gate_must_be_square_with_a_power_of_two_side(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="power-of-two side"):
        Gate("bad", np.zeros(shape, dtype=np.complex128))
