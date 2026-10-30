import numpy as np
import pytest

from mpi.exchange import Alone, Amplitudes, Exchange
from mpi.gates import Gate, H, T, X
from mpi.shard import Shard
from tests.mpi.lockstep import Lockstep, run


def dense(gate: Gate, on: tuple[int, ...], qubits: int) -> Amplitudes:
    """The gate as a matrix on the whole state, built by index arithmetic alone."""
    full = np.zeros((1 << qubits, 1 << qubits), dtype=np.complex128)
    for column in range(1 << qubits):
        gate_column = 0
        for position, qubit in enumerate(on):
            gate_column |= ((column >> qubit) & 1) << (gate.arity - 1 - position)
        for gate_row in range(1 << gate.arity):
            row = column
            for position, qubit in enumerate(on):
                bit = (gate_row >> (gate.arity - 1 - position)) & 1
                row = (row & ~(1 << qubit)) | (bit << qubit)
            full[row, column] = gate.matrix[gate_row, gate_column]
    return full


def random_state(qubits: int, seed: int = 7) -> Amplitudes:
    rng = np.random.default_rng(seed)
    state = rng.normal(size=1 << qubits) + 1j * rng.normal(size=1 << qubits)
    return np.asarray(state / np.linalg.norm(state), dtype=np.complex128)


def slice_of(state: Amplitudes, exchange: Exchange) -> Amplitudes:
    return np.array(state.reshape(exchange.size, -1)[exchange.rank])


def test_zero_state_is_one_amplitude_on_rank_zero() -> None:
    slices = run(4, lambda exchange: Shard.zero(5, exchange).amplitudes)
    state = np.concatenate(slices)
    assert len(state) == 32
    assert state[0] == 1
    assert not state[1:].any()


def test_ranks_must_number_a_power_of_two() -> None:
    with pytest.raises(ValueError, match="power of two"):
        Shard.zero(4, Lockstep(3).rank(0))


def test_ranks_cannot_outnumber_the_amplitudes() -> None:
    with pytest.raises(ValueError, match="at least 3 qubits"):
        Shard.zero(2, Lockstep(8).rank(0))


def test_a_slice_must_be_the_rank_s_share() -> None:
    with pytest.raises(ValueError, match="2\\*\\*2 amplitudes"):
        Shard(4, Lockstep(4).rank(1), np.zeros(8, dtype=np.complex128))


@pytest.mark.parametrize("gate", [H, T, X])
@pytest.mark.parametrize("qubit", [0, 2])
def test_a_local_gate_matches_the_dense_matrix(gate: Gate, qubit: int) -> None:
    state = random_state(3)
    shard = Shard(3, Alone(), state.copy())
    shard.apply(gate, (qubit,))
    assert np.allclose(shard.amplitudes, dense(gate, (qubit,), 3) @ state)


@pytest.mark.parametrize("qubit", [3, 4])
def test_a_gate_on_a_global_qubit_matches_the_dense_matrix(qubit: int) -> None:
    state = random_state(5)

    def body(exchange: Exchange) -> Amplitudes:
        shard = Shard(5, exchange, slice_of(state, exchange))
        shard.apply(H, (qubit,))
        return shard.amplitudes

    assert np.allclose(np.concatenate(run(4, body)), dense(H, (qubit,), 5) @ state)


def test_gates_compose_across_local_and_global_qubits() -> None:
    state = random_state(4)
    expected = dense(T, (0,), 4) @ dense(H, (3,), 4) @ dense(X, (2,), 4) @ state

    def body(exchange: Exchange) -> Amplitudes:
        shard = Shard(4, exchange, slice_of(state, exchange))
        shard.apply(X, (2,))
        shard.apply(H, (3,))
        shard.apply(T, (0,))
        return shard.amplitudes

    assert np.allclose(np.concatenate(run(4, body)), expected)


@pytest.mark.parametrize(
    ("gate", "on", "complaint"),
    [
        (H, (0, 1), "1 distinct qubits"),
        (H, (5,), "run from 0 to 3"),
        (Gate("swap", np.eye(4, dtype=np.complex128)), (1, 1), "2 distinct qubits"),
    ],
)
def test_qubits_must_fit_the_gate_and_the_state(
    gate: Gate, on: tuple[int, ...], complaint: str
) -> None:
    with pytest.raises(ValueError, match=complaint):
        Shard.zero(4, Alone()).apply(gate, on)


def test_two_global_qubits_in_one_gate_is_not_yet_supported() -> None:
    swap = Gate("swap", np.eye(4, dtype=np.complex128))
    with pytest.raises(ValueError, match="one global qubit"):
        Shard.zero(4, Lockstep(4).rank(0)).apply(swap, (2, 3))
