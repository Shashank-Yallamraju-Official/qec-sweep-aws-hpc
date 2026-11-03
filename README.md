# QEC sweep on AWS HPC

A quantum-error-correction decoder sweep, Stim sampling and PyMatching decoding, as the test cargo for a Slurm cluster on AWS that provisions itself, and the loop that makes every result it produces traceable and comparable. The design and the reasons behind it are in [docs/design.md](docs/design.md); the order of work, every commit and every measured number are in [docs/plan.md](docs/plan.md). Each directory below has its own README; this one is the map.

## The loop

A change to the cluster, the jobs or the code travels through a pull request. On the pull request, ParallelCluster validates the configuration against the account, the running cluster's head node runs a smoke job, Terraform plans, and a changed decoder manifest is judged against the one in force. On the merge, the job scripts are installed beside their commit, the cluster configuration is applied, and Terraform applies. A run then records what it used, under its own key in one bucket whose object versions cannot be deleted for a year; the catalogue folds those records into one table, and two runs are compared cell by cell with intervals. Nothing in the write-up is typed in by hand: every figure walks back to a record.

The loop was then measured and shortened. A timer reads, from those records and GitHub alone, how long a commit takes to become the first cell written on the cluster; against that baseline, nodes boot from an AMI with Apptainer and the images already on it, a pulled image is reused by digest, the grid runs its longest cells first, idle nodes go after three minutes instead of ten, and CI retags an image whose inputs did not change rather than rebuilding it. A Graviton cluster sits beside the x86 one for the cost per cell by instance type, and a plot puts loop time and cost per sweep before and after side by side.

The decoder loop closes the same way. Stim samples labelled syndrome histories as an array, a recurrent decoder trains on them with one rank per node, and the trained model is a choice of the sweep's cell contract beside PyMatching, so both decoders are judged through the same array, records, comparison and plot. One chain submits all of it wired by dependency, from the first sample to the comparison plot with no hand in between, under Stim's depolarising noise or a correlated variant, and every child run names the chain as a parent. The first chains ran in four minutes for a quarter of a dollar; the small recurrent decoder matches PyMatching at distance 3 and loses to it at distance 5, which the plan records as measured.

## Map

| Directory | What it is for |
| --- | --- |
| [`sweep/`](sweep/) | One call, one cell, one Parquet file: the unit of work, the grid, the reducer and the threshold plot |
| [`mpi/`](mpi/) | A state-vector simulator sharded across MPI ranks, for the tightly coupled runs |
| [`results/`](results/README.md) | The catalogue over every run's record, the comparison of two runs, and the check that admits a decoder manifest |
| [`models/`](models/README.md) | The decoder in force, as a manifest changed by pull request |
| [`web/`](web/README.md) | The comparison site: pick two runs, judge them cell by cell with intervals, trace each to its record; published to GitHub Pages on every merge |
| [`decoder/`](decoder/) | The labelled syndrome samples, the recurrent decoder, its training across nodes, a cell decoded with it, and the plot of both decoders |
| [`jobs/`](jobs/) | The Slurm scripts that submit a sweep, a scaling run or the decoder chain and write its record |
| [`cluster/`](cluster/) | The ParallelCluster configurations, x86 and Graviton, the AMI builds that bake Apptainer and the images, and the script each node runs as it boots |
| [`image/`](image/) | The Apptainer definitions CI builds into the images the jobs pull, for x86 and arm64 |
| [`infra/`](infra/) | Terraform for the bucket, the budget, the CI runners and the Systems Manager documents |
| [`tools/`](tools/) | The commit-message rule, the cost report, the process report, the loop timer and the before-and-after plot |
