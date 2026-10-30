# QEC Sweep on AWS HPC — Design

Oct 27, 2026 · @Shashank Yallamraju

## Purpose

This project runs a quantum error-correction (QEC) decoder sweep on an HPC cluster built on AWS entirely as code. It exists to answer one question: can a scientist describe a computation and get a reproducible, cost-governed result back without touching infrastructure?

The sweep itself is the test cargo. The deliverable is the platform around it: a Slurm cluster that provisions itself, a frozen environment, a job-array pattern for parameter sweeps, an MPI path for tightly coupled work, and a CI pipeline that treats the cluster as a versioned artifact.

Each stage adds one capability and reports one metric, so a reader can see what was added, why it was needed, and whether it worked.

## The workload

A QEC sweep estimates the logical error rate of a surface code across code distances and physical noise rates. One cell of the grid is one (distance d, noise rate p, shot count) triple: Stim samples syndromes, PyMatching decodes them, and the output is a single number plus its confidence interval.

It is a good HPC test case for three reasons.

- Cells are independent, so the grid is embarrassingly parallel and maps directly onto a Slurm job array. Throughput should scale linearly with nodes, which makes scaling easy to verify.
- Each cell is small (minutes, under 1 GB) but the grid is large (hundreds of cells), so scheduler behaviour, provisioning latency and I/O patterns matter more than raw FLOPS. That is the platform's job, not the code's.
- A tightly coupled variant exists in the same domain: a state-vector simulation sharded across ranks needs an all-to-all exchange on every non-local two-qubit gate. That gives the MPI stage a workload a quantum team would recognise rather than a toy.

The sweep's unit contract: `sweep --d 5 --p 1e-3 --shots 100000 --out <path>` writes one Parquet file named by its cell. Everything above that line is platform.

## Architecture

Architecture diagram: added with the README in stage 10.

The top lane is what changes with every commit; the bottom lane is what the commit produces. The sweep queue is the accent because it carries the primary workload; the MPI queue and DCV node are the two additions that go beyond MLOps.

| Component | Problem it solves | Why this choice |
| --- | --- | --- |
| ParallelCluster + Slurm | Nodes must appear when work is queued and vanish when idle | The AWS-native HPC scheduler; Slurm is what every HPC team already speaks |
| Two queues | Sweep cells and MPI jobs want different hardware | Spot c7a is cheap for independent cells; hpc7a with EFA is required for low-latency collectives |
| Apptainer image | A fresh node must match last week's node bit for bit | No root daemon, so it runs on shared clusters; built once in CI, pulled at job start |
| EFS | Nodes need one shared scratch filesystem for inputs, the image and job output | Chosen over FSx for Lustre because this account's plan cannot use FSx and the sweep writes one small file per cell; the parallel-I/O lesson is a known gap, recorded in the decisions table |
| S3 | Results must outlive the cluster | Durable, cheap, and what the next pipeline reads from |
| CI pipeline | Config drift and manual SSH | Validates the cluster YAML and builds the image on every PR; the cluster is a versioned artifact |
| Budget alerts + run records | Elastic compute makes cost a per-run number | Each run records its nodes and timing and is priced at the published rates, checked against Cost Explorer's daily total; grouping by tag needs the payer account, which this project does not hold |
| DCV login node | Scientists use GUI simulation tools | Amazon DCV is the AWS remote-visualisation path; optional here, proves the pattern |

## Build order

Each stage adds one capability from the diagram and ends with a done-signal. Stages 1 to 6 are the core; 7 and 8 are what make it a platform rather than a sweep that happened to run on AWS.

1. **Define the unit of work.** Refactor the sweep so one call is one cell, parameters from the CLI, output a Parquet file named by its cell. Done: runs locally against a local path. Metric: none yet; this fixes the contract.
2. **One node by hand.** A single EC2 instance, packages installed manually, one cell run, result copied to S3. Done: a file lands in S3 and every installed package is written down. Metric: the package list is the input to stage 3.
3. **Freeze the environment.** Build the Apptainer image in CI; rerun stage 2 from a fresh instance using only the image. Done: a bit-identical result. Metric: time-to-reproduce, from weeks of README-following to minutes.
4. **Stand up ParallelCluster.** Commit the cluster YAML: one head node, one Slurm queue, EFS scratch. Submit `srun hostname` across two nodes. Done: nodes appear when a job queues and vanish ten minutes after idle. Metric: time-to-first-node.
5. **Job array for the sweep.** One `sbatch --array` script maps task index to a (d, p) cell and runs the image; results to EFS, synced to S3 on exit. Done: the full grid completes and a logical-error-rate plot comes out. Metric: wall-clock for the sweep versus a laptop.
6. **Scale and cost it.** Rerun at 1, 4, 8 and 16 nodes, each run recording its nodes and timing; price the runs and check the total against Cost Explorer; add a spot queue beside on-demand. Done: a weak-scaling table and a cost-per-sweep figure. Metric: throughput per node and dollars per sweep.
7. **Add tight coupling.** A state-vector simulator sharded across MPI ranks (mpi4py first, C++ second) on an EFA-enabled hpc7a queue. Done: a strong-scaling plot with efficiency falling as nodes rise, and an account of where the time goes. Metric: strong-scaling efficiency at 2, 4, 8 nodes.
8. **Make the cluster a versioned artifact.** CI validates the cluster YAML, builds the image and runs a smoke job on every PR; Terraform owns IAM, S3 and the budget. Done: a node-type change reaches a running cluster through a pull request alone. Metric: changes shipped without SSH.
9. **Graphical node, optional.** A DCV-enabled login node running a GUI tool (ParaView is enough). Done: a remote desktop session opens from a browser. Metric: none; this proves the CAE pattern.
10. **Write it up.** README with the diagram above, the metrics table below and three paragraphs on what broke.

## Decisions and alternatives

Every choice below was made for a reason a reader of the README should be able to check against the alternative.

| Decision | Alternative considered | Why not the alternative |
| --- | --- | --- |
| Slurm via ParallelCluster | AWS Batch | Batch handles the job array well but has no MPI story and is not what HPC teams run; Slurm covers both queues with one scheduler |
| Slurm via ParallelCluster | Kubernetes with Kueue | Closer to MLOps muscle memory, but tightly coupled MPI on Kubernetes still needs an operator and EFA plumbing; the target team speaks Slurm |
| Apptainer | Docker | Docker needs a root daemon, which shared HPC nodes do not allow; Apptainer runs unprivileged and reads Docker images |
| Apptainer | Spack only | Spack is the right tool for compiled MPI stacks; it is kept in reserve for stage 7 and layered inside the image if needed |
| EFS | FSx for Lustre | Lustre was the first choice, striping across servers under hundreds of writers, but this account's plan cannot use FSx; the sweep writes one small Parquet file per cell, which EFS serves without strain, and the parallel-I/O lesson is deferred to a cluster that can use Lustre |
| EFS | S3 only | Fine for the sweep, wrong for MPI checkpoints, which need a shared filesystem the ranks can all reach |
| Spot for the sweep queue | On-demand everywhere | Cells are idempotent and short, so interruption costs one cell; spot cuts the sweep's bill by roughly two-thirds. This account's plan denies spot launches by policy, so the spot queue stays in the config for an account that allows them and the spot cost is priced from the spot price history rather than measured |
| On-demand for the MPI queue | Spot everywhere | One interrupted rank kills the whole MPI job |
| Terraform for surroundings | CDK | Either works; Terraform because the ParallelCluster YAML is already declarative and the two read alike |
| Parquet per cell | One big CSV | Independent files make tasks idempotent and retryable; a reducer concatenates at the end |

## What is measured

The README reports these numbers. They are blank until the stage that produces them runs; a reader can tell at a glance how far the project has got.

| Metric | Stage | How it is measured | Target |
| --- | --- | --- | --- |
| Time-to-reproduce environment (min) | 3 | Fresh instance to first successful cell, image only | under 10 |
| Time-to-first-node (min) | 4 | `sbatch` submit to node in `sinfo` idle state | under 5 |
| Sweep wall-clock (min) | 5, 6 | Array submit to last cell written, at 1, 4, 8, 16 nodes | near linear in nodes |
| Cost per sweep (USD) | 6 | Each run's node-seconds at the published on-demand and spot rates, checked against Cost Explorer's daily total | spot under one-third of on-demand |
| Weak-scaling efficiency (%) | 6 | Cells per node-hour at 16 nodes over 1 node | above 90 |
| Strong-scaling efficiency (%) | 7 | Fixed state-vector size, T(1) / (N x T(N)) at 2, 4, 8 | reported, with where time goes |
| Changes shipped without SSH | 8 | Count of merged PRs that reached the cluster | all of them |

The two scaling numbers are the ones an HPC reader will look for first; the cost number is the one a cloud reader will. Reporting both is the point of the project.

## Out of scope and guardrails

Out of scope, and said so to keep the README honest:

- Real quantum hardware or hardware-simulation tools such as HFSS or COMSOL; the DCV node proves the pattern with an open-source GUI.
- GPU state-vector simulation (cuQuantum); noted as the natural next stage.
- Multi-user fairness, accounting or authentication; this is a single-user cluster.
- Real-time decoding; the sweep is batch.

Cost guardrails, set before stage 2:

- AWS Budget alerts at 20 and 50 USD per month.
- Compute nodes scale to zero after 10 minutes idle; the head node is t3.medium.
- EFS is paid per gigabyte stored, holds only scratch, and is deleted with the cluster.
- Every job carries a cost-allocation tag so nothing is unattributed.
- `pcluster delete-cluster` at the end of every session; a scheduled check confirms nothing is left running.
