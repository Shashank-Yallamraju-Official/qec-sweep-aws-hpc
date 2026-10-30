"""One rank's slice of a state vector, and how a gate acts on it."""

from __future__ import annotations

from time import perf_counter

import numpy as np

from mpi.account import Account
from mpi.exchange import Amplitudes, Exchange
from mpi.gates import Gate
from mpi.kernel import KERNEL, Kernel


class Shard:
    """The amplitudes one rank holds of a state of ``qubits`` qubits.

    The ranks number a power of two, and rank ``r`` holds the amplitudes whose
    index has ``r`` in its top bits. Those top qubits are global, the rest local.
    A gate on local qubits is a local operation. A gate on global qubits first
    collects the slices of every rank that differs in those bits, so each holds
    every set of amplitudes the gate mixes, and keeps its own slice of the result.

    Attributes:
        account: Gates applied and time spent, kept as gates are applied.
    """

    def __init__(
        self, qubits: int, exchange: Exchange, amplitudes: Amplitudes, kernel: Kernel = KERNEL
    ) -> None:
        """Wrap this rank's slice of a state; ``zero`` makes the usual starting state."""
        self.qubits = qubits
        self.local_qubits = _local_qubits(qubits, exchange.size)
        if amplitudes.shape != (1 << self.local_qubits,) or amplitudes.dtype != np.complex128:
            msg = f"a slice is 2**{self.local_qubits} complex128 amplitudes, not {amplitudes.shape}"
            raise ValueError(msg)
        self.account = Account()
        self._exchange = exchange
        self._kernel = kernel
        self._amplitudes = amplitudes

    @classmethod
    def zero(cls, qubits: int, exchange: Exchange, kernel: Kernel = KERNEL) -> Shard:
        """The state with every qubit zero: one amplitude on rank 0, none elsewhere."""
        amplitudes = np.zeros(1 << _local_qubits(qubits, exchange.size), dtype=np.complex128)
        if exchange.rank == 0:
            amplitudes[0] = 1
        return cls(qubits, exchange, amplitudes, kernel)

    @property
    def rank(self) -> int:
        """The rank holding this slice."""
        return self._exchange.rank

    @property
    def amplitudes(self) -> Amplitudes:
        """This rank's slice, in index order."""
        return self._amplitudes

    def norm(self) -> float:
        """The norm of the whole state, on every rank; one, unless something went wrong."""
        own = float(np.vdot(self._amplitudes, self._amplitudes).real)
        return float(np.sqrt(self._exchange.total(own)))

    def apply(self, gate: Gate, on: tuple[int, ...]) -> None:
        """Apply ``gate`` to the qubits ``on``, the first listed most significant in its matrix.

        Raises:
            ValueError: If the qubits do not fit the gate or the state.
        """
        self._check(gate, on)
        started, exchanged = perf_counter(), self.account.exchange_seconds
        far = sorted((q for q in on if q >= self.local_qubits), reverse=True)
        group = self._collect(far)
        bits = [self._bit(q, far) for q in on]
        if far:
            slot = self._slot(far)
            self._kernel.mix(group, gate.matrix, bits, keep=slot)
            self._amplitudes = group[slot].copy()
        else:
            self._kernel.mix(group, gate.matrix, bits)
        swapped = self.account.exchange_seconds - exchanged
        self.account.gate(far=bool(far), compute_seconds=perf_counter() - started - swapped)

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
            started = perf_counter()
            self._exchange.swap(self._amplitudes, peer, into=group[slot ^ step])
            self.account.exchange_seconds += perf_counter() - started
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

    def _bit(self, qubit: int, far: list[int]) -> int:
        """The index bit of ``qubit`` in the stack ``_collect`` builds for ``far``."""
        if qubit in far:
            return self.local_qubits + len(far) - 1 - far.index(qubit)
        return qubit


def _local_qubits(qubits: int, ranks: int) -> int:
    if ranks < 1 or ranks & (ranks - 1):
        msg = f"ranks must number a power of two, not {ranks}"
        raise ValueError(msg)
    global_qubits = ranks.bit_length() - 1
    if qubits < global_qubits:
        msg = f"{ranks} ranks need at least {global_qubits} qubits, not {qubits}"
        raise ValueError(msg)
    return qubits - global_qubits
