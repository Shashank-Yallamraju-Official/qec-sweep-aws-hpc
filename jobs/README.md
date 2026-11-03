# jobs

The Slurm scripts. Each `*.sh` submits one kind of run from the head node and writes the run's record; each `*.sbatch` is what one task does on a node, inside an image. A run is a directory on shared scratch, `/scratch/<user>/<kind>/<timestamp>`, and a `sync` job copies it under the same key in S3 when the run ends.

## Runs

| Script | Submits |
| --- | --- |
| `sweep.sh [-s seed] [-t type] <image> s3://bucket/sweeps [queue] [nodes]` | the whole grid as one array, longest cells first |
| `weak-scaling.sh <image> s3://bucket/sweeps <queue> <nodes>...` | the grid at each node count in turn |
| `strong-scaling.sh <image> s3://bucket/statevector <queue> <ranks> <qubits> <layers> <nodes>...` | the state-vector circuit at each node count |
| `generate.sh [-n noise] [-c chunks] <image> s3://bucket/generate <queue> <shots> <d:p>...` | labelled samples as an array |
| `train.sh [-n nodes] [-a job] <image> s3://bucket/train <samples> [queue]` | one training, one rank per node |
| `evaluate.sh [-D learned -m d=model] [-a job] <image> s3://bucket/evaluations <queue> <shots> <d:p>...` | named cells decoded by one decoder |
| `chain.sh <sweep image> <train image> s3://bucket <queue> <shots> <shots> <d:p>...` | generate, train, evaluate both and compare, wired by dependency |

Every record names the image URI and the digest it resolved to, the commit the scripts came from, the cluster configuration's hash, the job ids, the seed and the runs this one was made from, so an audit walks back through keys alone. `pull-image.sh` fetches an image once per digest into a cache every node reads.

## Where it fits

The deploy workflow installs this directory on the head node as `/opt/qec/jobs` with its commit beside it, through a Systems Manager document in [`infra/`](../infra/README.md). The images come from [`image/`](../image/README.md); the records are read by [`results/`](../results/README.md). The scripts are tested against stand-ins for `sbatch`, `srun` and `apptainer`: `uv run pytest tests/jobs`.
