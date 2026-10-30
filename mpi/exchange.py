"""How a rank trades its amplitudes with the ranks a gate mixes them with."""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

type Amplitudes = NDArray[np.complex128]


class Exchange(Protocol):
    """Pairwise exchange of equal-sized buffers between numbered ranks, and two reductions."""

    @property
    def rank(self) -> int:
        """This rank's number, from zero."""

    @property
    def size(self) -> int:
        """How many ranks there are."""

    def swap(self, send: Amplitudes, peer: int, into: Amplitudes) -> None:
        """Send a buffer to ``peer`` and receive the one it sends into ``into``.

        Every swap is mutual: ``peer`` must be swapping with this rank in the
        same step, or both wait forever.
        """

    def maximum(self, value: float) -> float:
        """The largest ``value`` any rank passes, on every rank."""

    def total(self, value: float) -> float:
        """The sum of ``value`` over the ranks, on every rank."""


class Alone:
    """The single rank of a run without MPI: it holds the whole state and has no peers."""

    rank = 0
    size = 1

    def swap(self, send: Amplitudes, peer: int, into: Amplitudes) -> None:
        """Fail: a single rank has nobody to swap with."""
        msg = f"rank 0 of 1 cannot swap {send.size} amplitudes with peer {peer} for {into.size}"
        raise LookupError(msg)

    def maximum(self, value: float) -> float:
        """The value itself: there is no other rank."""
        return value

    def total(self, value: float) -> float:
        """The value itself: there is no other rank."""
        return value


class World:
    """All the ranks under ``mpiexec``, through mpi4py."""

    def __init__(self) -> None:
        # Importing mpi4py initialises MPI, which only a process under mpiexec should do.
        from mpi4py import MPI  # noqa: PLC0415

        self._comm = MPI.COMM_WORLD
        self._max, self._sum = MPI.MAX, MPI.SUM

    @property
    def rank(self) -> int:
        """This rank's number, from zero."""
        return int(self._comm.Get_rank())

    @property
    def size(self) -> int:
        """How many ranks there are."""
        return int(self._comm.Get_size())

    def swap(self, send: Amplitudes, peer: int, into: Amplitudes) -> None:
        """Send to ``peer`` and receive from it in one call, so neither side waits on the other."""
        self._comm.Sendrecv(send, dest=peer, recvbuf=into, source=peer)

    def maximum(self, value: float) -> float:
        """The largest ``value`` any rank passes, on every rank."""
        return float(self._comm.allreduce(value, op=self._max))

    def total(self, value: float) -> float:
        """The sum of ``value`` over the ranks, on every rank."""
        return float(self._comm.allreduce(value, op=self._sum))
