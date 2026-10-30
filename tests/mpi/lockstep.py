"""Ranks as threads that swap at a barrier, so sharded code runs in one process."""

from __future__ import annotations

import threading
from collections.abc import Callable

from mpi.exchange import Amplitudes, Exchange


class Lockstep:
    """A fixed number of ranks whose swaps meet at a barrier.

    Every rank must make the same sequence of swaps, as it must under MPI;
    a rank that swaps out of step hangs the others, which is the bug it would
    be under MPI too.
    """

    def __init__(self, size: int) -> None:
        self.size = size
        self._barrier = threading.Barrier(size)
        self._mailbox: dict[tuple[int, int], Amplitudes] = {}
        self._values: dict[int, float] = {}

    def rank(self, rank: int) -> Rank:
        return Rank(self, rank)

    def swap(self, rank: int, send: Amplitudes, peer: int) -> Amplitudes:
        self._mailbox[rank, peer] = send
        self._barrier.wait()
        received = self._mailbox[peer, rank]
        self._barrier.wait()
        return received

    def reduce(self, rank: int, value: float, combine: Callable[[list[float]], float]) -> float:
        self._values[rank] = value
        self._barrier.wait()
        result = combine([self._values[r] for r in range(self.size)])
        self._barrier.wait()
        return result

    def abort(self) -> None:
        self._barrier.abort()


class Rank:
    """One rank's view of a ``Lockstep``, satisfying ``Exchange``."""

    def __init__(self, world: Lockstep, rank: int) -> None:
        self._world = world
        self.rank = rank

    @property
    def size(self) -> int:
        return self._world.size

    def swap(self, send: Amplitudes, peer: int) -> Amplitudes:
        return self._world.swap(self.rank, send, peer)

    def maximum(self, value: float) -> float:
        return self._world.reduce(self.rank, value, max)

    def total(self, value: float) -> float:
        return self._world.reduce(self.rank, value, sum)


def run[T](size: int, body: Callable[[Exchange], T]) -> list[T]:
    """Run ``body`` on every rank at once and return the results in rank order."""
    world = Lockstep(size)
    results: dict[int, T] = {}
    errors: list[BaseException] = []

    def on(rank: int) -> None:
        try:
            results[rank] = body(world.rank(rank))
        except BaseException as error:  # noqa: BLE001
            errors.append(error)
            world.abort()

    threads = [threading.Thread(target=on, args=(rank,)) for rank in range(size)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise errors[0]
    return [results[rank] for rank in range(size)]
