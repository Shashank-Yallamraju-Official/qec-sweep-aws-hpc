# QEC sweep on AWS HPC

A quantum-error-correction decoder sweep, Stim sampling and PyMatching decoding, as the test cargo for a Slurm cluster on AWS that provisions itself, and the loop that makes every result it produces traceable and comparable. The design and the reasons behind it are in [docs/design.md](docs/design.md); the order of work, every commit and every measured number are in [docs/plan.md](docs/plan.md). Each directory below has its own README; this one is the map.

## The loop

A change to the cluster, the jobs or the code travels through a pull request. On the pull request, ParallelCluster validates the configuration against the account, the running cluster's head node runs a smoke job, Terraform plans, and a changed decoder manifest is judged against the one in force. On the merge, the job scripts are installed beside their commit, the cluster configuration is applied, and Terraform applies. A run then records what it used, under its own key in one bucket whose object versions cannot be deleted for a year; the catalogue folds those records into one table, and two runs are compared cell by cell with intervals. Nothing in the write-up is typed in by hand: every figure walks back to a record.

## Map

| Directory | What it is for |
| --- | --- |
| [`sweep/`](sweep/) | One call, one cell, one Parquet file: the unit of work, the grid, the reducer and the threshold plot |
| [`mpi/`](mpi/) | A state-vector simulator sharded across MPI ranks, for the tightly coupled runs |
| [`results/`](results/README.md) | The catalogue over every run's record, the comparison of two runs, and the check that admits a decoder manifest |
| [`models/`](models/README.md) | The decoder in force, as a manifest changed by pull request |
| [`jobs/`](jobs/) | The Slurm scripts that submit a sweep or a scaling run and write its record |
| [`cluster/`](cluster/) | The ParallelCluster configuration and the script each node runs as it boots |
| [`image/`](image/) | The Apptainer definitions CI builds into the images the jobs pull |
| [`infra/`](infra/) | Terraform for the bucket, the budget, the CI runners and the Systems Manager documents |
| [`tools/`](tools/) | The commit-message rule, the cost report and the process report |
