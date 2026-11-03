# mpi

The tightly coupled workload: a state vector sharded across MPI ranks, with a brickwork circuit applied layer by layer. A two-qubit gate on a qubit held across ranks needs an all-to-all exchange of amplitudes, which is what makes this a test of the network rather than of the cores. It exists so the platform's MPI queue, EFA and placement group have something real to carry.

## Commands

```sh
mpirun -n 64 statevector --qubits 28 --layers 8 --out records/   # rank 0 writes nodesN.json
statevector-plot records/ strong-scaling.png                     # efficiency against node count
```

Each run's record says how many qubits and layers, how many ranks, and where the time went: seconds computing against seconds exchanging, per layer. The strong-scaling plot reads a directory of those records, one per node count.

## Modules

`shard.py` is one rank's slice of the state and how a gate acts on it. `gates.py` are the matrices. `circuit.py` is the brickwork circuit. `exchange.py` is how a rank trades amplitudes with the ranks a gate mixes them with. `kernel.py` applies a gate in one C++ pass when its library is built, else in numpy. `account.py` keeps the time. `cli.py` and `plot.py` are the two commands.

## Where it fits

[`jobs/`](../jobs/README.md) runs it through `statevector.sbatch` and `strong-scaling.sh` inside the MPI image, which carries the EFA libfabric and the same Open MPI as the nodes. Install with `uv sync --extra mpi`; test with `uv run pytest tests/mpi`.
