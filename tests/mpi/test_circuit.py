from mpi.circuit import brickwork
from mpi.gates import CNOT, H, T


def test_each_layer_is_one_single_qubit_gate_per_qubit_then_the_cnot_brick() -> None:
    operations = brickwork(5, 2)
    even = operations[: 5 + 2]
    odd = operations[5 + 2 :]
    assert [(gate.name, on) for gate, on in even] == [
        *[(H.name, (q,)) for q in range(5)],
        (CNOT.name, (0, 1)),
        (CNOT.name, (2, 3)),
    ]
    assert [(gate.name, on) for gate, on in odd] == [
        *[(T.name, (q,)) for q in range(5)],
        (CNOT.name, (1, 2)),
        (CNOT.name, (3, 4)),
    ]


def test_every_neighbouring_pair_meets_within_two_layers() -> None:
    pairs = {on for gate, on in brickwork(8, 2) if gate is CNOT}
    assert pairs == {(q, q + 1) for q in range(7)}


def test_no_layers_is_no_gates() -> None:
    assert brickwork(4, 0) == []
