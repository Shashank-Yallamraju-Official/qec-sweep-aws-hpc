"""One rank's slice of a state vector, and how a gate acts on it."""

from __future__ import annotations

import numpy as np

from mpi.exchange import Amplitudes, Exchange
from mpi.gates import Gate


class Shard:
    """The amplitudes one rank holds of a state of ``qubits`` qubits.

    The ranks number a power of two, and rank ``r`` holds the amplitudes whose
    index has ``r`` in its top bits. Those top qubits are global, the rest local.
    A gate on local qubits is a local operation. A gate on a global qubit first
    swaps slices with the rank that differs in that bit, so both hold every
    pair of amplitudes the gate mixes.
    """

    def __init__(self, qubits: int, exchange: Exchange, amplitudes: Amplitudes) -> None:
        """Wrap this rank's slice of a state; ``zero`` makes the usual starting state."""
        self.qubits = qubits
        self.local_qubits = _local_qubits(qubits, exchange.size)
        if amplitudes.shape != (1 << self.local_qubits,):
            msg = f"a rank holds 2**{self.local_qubits} amplitudes here, not {len(amplitudes)}"
            raise ValueError(msg)
        self._exchange = exchange
        self._amplitudes = amplitudes

    @classmethod
    def zero(cls, qubits: int, exchange: Exchange) -> Shard:
        """The state with every qubit zero: one amplitude on rank 0, none elsewhere."""
        amplitudes = np.zeros(1 << _local_qubits(qubits, exchange.size), dtype=np.complex128)
        if exchange.rank == 0:
            amplitudes[0] = 1
        return cls(qubits, exchange, amplitudes)

    @property
    def rank(self) -> int:
        """The rank holding this slice."""
        return self._exchange.rank

    @property
    def amplitudes(self) -> Amplitudes:
        """This rank's slice, in index order."""
        return self._amplitudes

    def apply(self, gate: Gate, on: tuple[int, ...]) -> None:
        """Apply ``gate`` to the qubits ``on``, the first listed most significant in its matrix.

        Raises:
            ValueError: If the qubits do not fit the gate or the state.
        """
        self._check(gate, on)
        far = sorted((q for q in on if q >= self.local_qubits), reverse=True)
        group = self._collect(far)
        tensor = group.reshape((2,) * (len(far) + self.local_qubits))
        axes = [self._axis(q, far) for q in on]
        operator = gate.matrix.reshape((2,) * (2 * gate.arity))
        mixed = np.tensordot(operator, tensor, axes=(list(range(gate.arity, 2 * gate.arity)), axes))
        mixed = np.moveaxis(mixed, list(range(gate.arity)), axes)
        self._amplitudes = mixed.reshape(len(group), -1)[self._slot(far)].copy()

    def _check(self, gate: Gate, on: tuple[int, ...]) -> None:
        if len(on) != gate.arity or len(set(on)) != len(on):
            msg = f"{gate.name} acts on {gate.arity} distinct qubits, not {on}"
            raise ValueError(msg)
        if any(not 0 <= q < self.qubits for q in on):
            msg = f"qubits run from 0 to {self.qubits - 1}, not {on}"
            raise ValueError(msg)
        if sum(q >= self.local_qubits for q in on) > 1:
            msg = f"a gate may touch one global qubit, not {on} with {self.local_qubits} local"
            raise ValueError(msg)

    def _collect(self, far: list[int]) -> Amplitudes:
        """Stack this slice with the partner's when ``far`` names a global qubit."""
        if not far:
            return self._amplitudes[np.newaxis]
        bit = far[0] - self.local_qubits
        group = np.empty((2, len(self._amplitudes)), dtype=np.complex128)
        group[self._slot(far)] = self._amplitudes
        group[1 - self._slot(far)] = self._exchange.swap(self._amplitudes, self.rank ^ (1 << bit))
        return group

    def _slot(self, far: list[int]) -> int:
        """Where this rank's slice sits in the stack ``_collect`` builds for ``far``."""
        return (self.rank >> (far[0] - self.local_qubits)) & 1 if far else 0

    def _axis(self, qubit: int, far: list[int]) -> int:
        """The axis of ``qubit`` once the stack is reshaped to one axis per qubit."""
        if qubit in far:
            return far.index(qubit)
        return len(far) + self.local_qubits - 1 - qubit


def _local_qubits(qubits: int, ranks: int) -> int:
    if ranks < 1 or ranks & (ranks - 1):
        msg = f"ranks must number a power of two, not {ranks}"
        raise ValueError(msg)
    global_qubits = ranks.bit_length() - 1
    if qubits < global_qubits:
        msg = f"{ranks} ranks need at least {global_qubits} qubits, not {qubits}"
        raise ValueError(msg)
    return qubits - global_qubits
