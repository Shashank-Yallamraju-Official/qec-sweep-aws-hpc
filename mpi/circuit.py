"""The brickwork circuit the scaling runs apply."""

from __future__ import annotations

from mpi.gates import CNOT, Gate, H, T

type Operation = tuple[Gate, tuple[int, ...]]


def brickwork(qubits: int, layers: int) -> list[Operation]:
    """A circuit of ``layers`` layers on ``qubits`` qubits, as gates in order.

    Each layer puts one single-qubit gate on every qubit, H on even layers and
    T on odd, then CNOT on neighbouring pairs starting at the layer's parity, so
    over two layers every qubit meets both its neighbours. The pairs that span
    the global qubits are what make the circuit cost exchanges as ranks grow.
    """
    operations: list[Operation] = []
    for layer in range(layers):
        single = H if layer % 2 == 0 else T
        operations.extend((single, (qubit,)) for qubit in range(qubits))
        operations.extend((CNOT, (qubit, qubit + 1)) for qubit in range(layer % 2, qubits - 1, 2))
    return operations
