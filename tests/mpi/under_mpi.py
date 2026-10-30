"""Runs a fixed circuit on the ranks under ``mpiexec`` and writes each rank's slice.

usage: mpiexec -n <ranks> python -m tests.mpi.under_mpi <qubits> <directory>
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from mpi.exchange import World
from mpi.gates import CNOT, CZ, H, T
from mpi.shard import Shard


def main() -> None:
    qubits, directory = int(sys.argv[1]), Path(sys.argv[2])
    world = World()
    shard = Shard.zero(qubits, world)
    for qubit in range(qubits):
        shard.apply(H, (qubit,))
    for qubit in range(qubits - 1):
        shard.apply(CNOT, (qubit, qubit + 1))
    for qubit in range(qubits):
        shard.apply(T, (qubit,))
    for qubit in range(0, qubits - 1, 2):
        shard.apply(CZ, (qubit + 1, qubit))
    shard.apply(CNOT, (qubits - 1, 0))
    np.save(directory / f"rank{world.rank}.npy", shard.amplitudes)


if __name__ == "__main__":
    main()
