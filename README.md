# QEC sweep on AWS HPC

An ML platform that proves its own results, with a quantum error-correction decoder sweep as the cargo. A Slurm cluster on AWS that exists only while work runs, an environment frozen into images, a record for every run that cannot be deleted for a year, and a comparison of any two runs with confidence intervals, in the browser, with no server behind it. Every change travels through a pull request and every number below walks back to the run that produced it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/figures/loop-dark.svg">
  <img alt="One change, from a pull request to a comparison: a researcher opens a pull request on GitHub, GitHub Actions validates the cluster and builds the image, the merge deploys to AWS ParallelCluster, a sweep runs and writes its record and cells to Amazon S3, and the site on GitHub Pages compares two runs." src="docs/figures/loop-light.svg">
</picture>

The design and the reasons behind every choice are in [docs/design.md](docs/design.md); the order of work, every commit and every measured number are in [docs/plan.md](docs/plan.md). Each directory has its own README, a minute's reading; this one is the map.

## The loop

A change to the cluster, the jobs or the code travels through a pull request (steps 1 to 4 in the figure). ParallelCluster validates the configuration against the account, the running cluster's head node runs a smoke job, Terraform plans, and a changed decoder manifest is judged against the one in force. On the merge (5 to 7), the job scripts are installed beside their commit, the cluster configuration is applied, and Terraform applies. A run (8 to 10) records what it used under its own key in one bucket whose object versions cannot be deleted for a year; the catalogue folds those records into one table, and the site (11 and 12) compares two runs cell by cell with intervals.

The loop was then measured and shortened. A timer reads, from those records and GitHub alone, how long a commit takes to become the first cell written on the cluster; against that baseline, nodes boot from an AMI with Apptainer and the images already on it, a pulled image is reused by digest, the grid runs its longest cells first, idle nodes go after three minutes instead of ten, and CI retags an image whose inputs did not change rather than rebuilding it. A Graviton cluster sits beside the x86 one for the cost per cell by instance type.

The decoder loop closes the same way. Stim samples labelled syndrome histories as an array, a recurrent decoder trains on them with one rank per node, and the trained model is a choice of the sweep's cell contract beside PyMatching, so both decoders are judged through the same array, records, comparison and plot. One chain submits all of it wired by dependency, from the first sample to the comparison plot with no hand in between.

The last stage uses the platform the way a scientist would and writes down how. An experiment is one pass of a fixed loop, recorded under [`experiments/`](experiments/README.md): where things stand, read from the last chain's records by `decoder-diagnose`; the causes the numbers support; the candidate changes with their predicted effect and cost; the one chosen, by the researcher; a prediction with its threshold and budget, committed before anything runs; then the run, the result against the prediction, and what follows. A commit hook refuses a record with a section missing or a result whose commits predate its prediction. The process itself is versioned in the directory's README, with a table of what changed and which experiment made it change. The first pass asked whether the stage 12 decoder was short of data or of capacity, and answered it: at 5,000,000 training shots the same model is below matching at every rate.

## Numbers

Each stage ends with one measurement. The full account of each, with what it is compared against and what was learned, is in the plan's table; these are the headlines.

| Stage | Measured | Result |
| --- | --- | --- |
| 3, frozen environment | time to reproduce a result on a fresh node from the image alone | 3.7 min |
| 4, cluster | `sbatch` to the first node allocated, from a powered-down queue | 4.0 min; 3.2 min once the AMI was baked |
| 5, job array | the 200-cell grid on four cold nodes, against a ten-core laptop | 7.3 min against 1.4 min; 5.1 min of it was nodes booting |
| 6, scale and cost | cells per node-hour at 1 and 16 nodes | 1478 and 887, then 1507 at 16 nodes once the grid ran longest cells first |
| 7, tight coupling | strong-scaling efficiency at 2 and 16 nodes over TCP, 25 qubits | 61% and 21%; the exchanges take three quarters of the time at 16 |
| 8, cluster as code | changes shipped to a running cluster without SSH | every change since, through a pull request |
| 9, graphical node | a remote desktop from a browser | ParaView on the login node, through a Session Manager tunnel, no warning |
| 12, decoder loop | the learned decoder's error rate over PyMatching's, distance 5 | 3.7 to 12.6 times worse on 200,000 training shots; the chain ran unattended in 4.3 min for $0.24 |
| 13, provenance | figures that resolve through S3 keys alone to a complete record | 16 of 21 |
| 14, comparison site | Lighthouse performance on a throttled phone; the comparison query | 100; 11 ms median in the browser |
| 15, shorter loop | the platform's share of commit to first cell, and dollars per 16-node sweep | 5.6 min from 6.4; $0.098 from $0.30 |
| 16, research loop | the same decoder's error rate over PyMatching's at distance 5, against training shots | 3.05, 1.60 and 0.90 at 200k, 1M and 5M shots; below matching at every rate with 5M, for $1.48 |

## What broke

The account said no twice. Every HPC and accelerated-instance quota in the project is zero, the GPU request was refused and the HPC one stalled in review, so the EFA points of the MPI stage and the whole GPU stage wait on appeals; the design routes around them, with the interfaces built so a GPU queue plugs in the day it exists, and the strong-scaling result is reported over TCP as provisional rather than left out. The organisation's managed policy also denies every IAM identity-provider action, which rules out GitHub's own federation into AWS; the runners are CodeBuild projects carrying roles instead, a read-only one for a pull request and a deploying one for `main`.

The platform's defaults fought the work in small ways that each cost an afternoon. Slurm hands tasks to nodes that are still powering up, so a sixteen-node run started mid-boot measured provisioning instead of decoding. Stim and PyMatching ship no arm64 wheels, so the Graviton image compiles them. The three-minute scale-down that made a sweep cheap made a chained run slow: nodes idled past it while a job waited on a dependency and had to boot again. DCV accepts a certificate only at mode 600 and otherwise falls back to its own without a word.

The decoder did not win at first. A two-layer LSTM of 64 units, the published recipe, matched PyMatching at distance 3 and lost to it at distance 5 under both noise models on 200,000 training shots and ten epochs, with training accuracy equal to held-out accuracy: underfit, not overfit. The plan recorded the ratios with their intervals rather than tuning until the row read well. The research loop of stage 16 then asked the question that result posed, data or capacity, and registered a prediction before running: trained on 200,000, 1,000,000 and 5,000,000 shots until its held-out loss stalled, the same model went from 3.05 times matching's error rate to 0.90, and below matching at every rate, including the two it never trained on, which the prediction had said would not happen. One training seed so far; the process now demands a second before a win is called.

## Map

| Directory | What it is for |
| --- | --- |
| [`sweep/`](sweep/README.md) | One call, one cell, one Parquet file: the unit of work, the grid, the reducer and the threshold plot |
| [`mpi/`](mpi/README.md) | A state-vector simulator sharded across MPI ranks, for the tightly coupled runs |
| [`decoder/`](decoder/README.md) | The labelled syndrome samples, the recurrent decoder, its training across nodes, a cell decoded with it, and the plot of both decoders |
| [`results/`](results/README.md) | The catalogue over every run's record, the comparison of two runs, and the check that admits a decoder manifest |
| [`models/`](models/README.md) | The decoder in force, as a manifest changed by pull request |
| [`web/`](web/README.md) | The comparison site: pick two runs, judge them cell by cell with intervals, trace each to its record; published to GitHub Pages on every merge |
| [`jobs/`](jobs/README.md) | The Slurm scripts that submit a sweep, a scaling run or the decoder chain and write its record |
| [`cluster/`](cluster/README.md) | The ParallelCluster configurations, x86 and Graviton, the AMI builds, the login node's desktop, and the script each node runs as it boots |
| [`image/`](image/README.md) | The Apptainer definitions CI builds into the images the jobs pull, for x86 and arm64 |
| [`infra/`](infra/README.md) | Terraform for the bucket, the node roles, the CI runners, the Systems Manager documents and the cost guardrails |
| [`tools/`](tools/README.md) | The commit-message rule, the cost report, the process report, the loop timer, the before-and-after plot, the figure above and the experiment records' tool |
| [`experiments/`](experiments/README.md) | The research loop: the process, versioned, and one record per experiment with its prediction committed before its run |
