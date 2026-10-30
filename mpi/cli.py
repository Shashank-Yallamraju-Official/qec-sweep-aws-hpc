"""The ``statevector`` command: run the brickwork circuit across the ranks and record the run."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

from mpi.circuit import brickwork
from mpi.exchange import Exchange, World
from mpi.shard import Shard


def main(argv: Sequence[str] | None = None, exchange: Exchange | None = None) -> int:
    """Run the circuit on every rank and have rank 0 write the record.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.
        exchange: The ranks to run on; ``None`` means all the ranks under ``mpiexec``.

    Returns:
        Exit status: 0 on success, 2 when the state does not fit the ranks.
    """
    parser = argparse.ArgumentParser(
        prog="statevector", description="apply a brickwork circuit to a sharded state vector"
    )
    parser.add_argument("--qubits", type=int, required=True, help="qubits in the state")
    parser.add_argument("--layers", type=int, default=4, help="layers of the circuit")
    parser.add_argument("--out", type=Path, required=True, help="where rank 0 writes the record")
    args = parser.parse_args(argv)
    exchange = exchange if exchange is not None else World()
    try:
        record = run(args.qubits, args.layers, exchange)
    except ValueError as error:
        print(f"statevector: {error}", file=sys.stderr)
        return 2
    if exchange.rank == 0:
        args.out.write_text(json.dumps(record, indent=2) + "\n")
        print(args.out)
    return 0


def run(qubits: int, layers: int, exchange: Exchange) -> dict[str, object]:
    """Apply the circuit and return the record: sizes, gate counts, and the slowest rank's seconds.

    Raises:
        ValueError: If the ranks do not fit the state.
    """
    shard = Shard.zero(qubits, exchange)
    started = perf_counter()
    for gate, on in brickwork(qubits, layers):
        shard.apply(gate, on)
    elapsed = perf_counter() - started
    account = shard.account
    return {
        "qubits": qubits,
        "layers": layers,
        "ranks": exchange.size,
        "gates": {"local": account.local_gates, "far": account.far_gates},
        "seconds": {
            "total": exchange.maximum(elapsed),
            "compute": exchange.maximum(account.compute_seconds),
            "exchange": exchange.maximum(account.exchange_seconds),
        },
        "norm": shard.norm(),
    }


if __name__ == "__main__":
    sys.exit(main())
