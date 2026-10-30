import numpy as np
import pytest

from mpi.gates import CNOT, CZ, Gate, H, T, X


@pytest.mark.parametrize("gate", [H, T, X])
def test_single_qubit_gates_are_unitary(gate: Gate) -> None:
    assert gate.arity == 1
    assert np.allclose(gate.matrix @ gate.matrix.conj().T, np.eye(2))


@pytest.mark.parametrize("gate", [CNOT, CZ])
def test_two_qubit_gates_are_unitary(gate: Gate) -> None:
    assert gate.arity == 2
    assert np.allclose(gate.matrix @ gate.matrix.conj().T, np.eye(4))


def test_cnot_flips_the_second_qubit_when_the_first_is_set() -> None:
    assert np.array_equal(CNOT.matrix @ np.eye(4)[2], np.eye(4)[3])
    assert np.array_equal(CNOT.matrix @ np.eye(4)[1], np.eye(4)[1])


@pytest.mark.parametrize("shape", [(2, 3), (3, 3), (1, 1), (4,)])
def test_a_gate_must_be_square_with_a_power_of_two_side(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="power-of-two side"):
        Gate("bad", np.zeros(shape, dtype=np.complex128))
