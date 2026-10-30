"""One rank's slice of a state vector, and how a gate acts on it."""

from __future__ import annotations

import numpy as np

from mpi.exchange import Amplitudes, Exchange
from mpi.gates import Gate


class Shard:
    """The amplitudes one rank holds of a state of ``qubits`` qubits.

    The ranks number a power of two, and rank ``r`` holds the amplitudes whose
    index has ``r`` in its top bits. Those top qubits are global, the rest local.
    A gate on local qubits is a local operation. A gate on global qubits first
    collects the slices of every rank that differs in those bits, so each holds
    every set of amplitudes the gate mixes, and keeps its own slice of the result.
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

    def _collect(self, far: list[int]) -> Amplitudes:
        """Stack this slice with those of every rank differing in the global qubits ``far``.

        Slot ``i`` holds the slice of the rank whose bits for ``far`` spell ``i``.
        Step ``s`` swaps with the rank at slot ``i xor s``, so every step pairs
        each rank of the group with exactly one other and none waits on a third.
        """
        if not far:
            return self._amplitudes[np.newaxis]
        slot = self._slot(far)
        group = np.empty((1 << len(far), len(self._amplitudes)), dtype=np.complex128)
        group[slot] = self._amplitudes
        for step in range(1, len(group)):
            peer = self._rank_at(far, slot ^ step)
            group[slot ^ step] = self._exchange.swap(self._amplitudes, peer)
        return group

    def _slot(self, far: list[int]) -> int:
        """Where this rank's slice sits in the stack ``_collect`` builds for ``far``."""
        slot = 0
        for qubit in far:
            slot = (slot << 1) | ((self.rank >> (qubit - self.local_qubits)) & 1)
        return slot

    def _rank_at(self, far: list[int], slot: int) -> int:
        """The rank in this one's group whose bits for ``far`` spell ``slot``."""
        rank = self.rank
        for position, qubit in enumerate(far):
            bit = qubit - self.local_qubits
            value = (slot >> (len(far) - 1 - position)) & 1
            rank = (rank & ~(1 << bit)) | (value << bit)
        return rank

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
