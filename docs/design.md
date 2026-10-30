# QEC Sweep on AWS HPC — Design

Oct 27, 2026 · @Shashank Yallamraju

## Purpose

This project runs a quantum error-correction (QEC) decoder sweep on an HPC cluster built on AWS entirely as code. It exists to answer one question: can a scientist describe a computation and get a reproducible, cost-governed result back without touching infrastructure?

The sweep itself is the test cargo. The deliverable is the platform around it: a Slurm cluster that provisions itself, a frozen environment, a job-array pattern for parameter sweeps, an MPI path for tightly coupled work, a CI pipeline that treats the cluster as a versioned artifact, a GPU path that runs the same tightly coupled simulation on the hardware a quantum team would use for it, a decoder-training loop that ties the queues into one pipeline, results that are themselves a versioned, auditable artifact, a comparison site that puts two runs side by side in the browser with nothing behind the page, and a last pass that measures how much shorter and cheaper the whole loop can be made.

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
| Three queues | Sweep cells, MPI jobs and GPU jobs want different hardware | Spot c7a is cheap for independent cells; an HPC instance type with EFA is required for low-latency collectives. hpc6a, not hpc7a as first planned: two fifths of the price for the same scaling question. Either needs a private subnet and a NAT gateway, since an EFA node carries a second interface and EC2 gives no public IP to an instance with two. The GPU queue is `g6.12xlarge`, four L4 cards in one node: the smallest instance that holds a thirty-qubit state in single precision on one card and still has several cards to scale across; a `p4d` with NVLink and EFA is the optional last point if its quota and price allow |
| Apptainer image | A fresh node must match last week's node bit for bit | No root daemon, so it runs on shared clusters; built once in CI, pulled at job start |
| EFS | Nodes need one shared scratch filesystem for inputs, the image and job output | Chosen over FSx for Lustre because this account's plan cannot use FSx and the sweep writes one small file per cell; the parallel-I/O lesson is a known gap, recorded in the decisions table |
| S3 | Results must outlive the cluster | Durable, cheap, and what the next pipeline reads from |
| CI pipeline | Config drift and manual SSH | Validates the cluster YAML and builds the image on every PR; the cluster is a versioned artifact |
| Budget alerts + run records | Elastic compute makes cost a per-run number | Each run records its nodes and timing and is priced at the published rates, checked against Cost Explorer's daily total; grouping by tag needs the payer account, which this project does not hold |
| Run records, catalogue, report | A result must be comparable with last month's and traceable to what produced it | Each run writes its record and outputs under its own S3 key, naming the commit, image digest, seeds and parent runs; a catalogue table over those records answers questions through DuckDB without a server. MLflow or Weights & Biases would do the same with a server or a SaaS account and a second source of truth |
| Comparison site | Two runs must be put side by side, with intervals and provenance, by someone who will not open a terminal | A static site built with Vite and Svelte that loads DuckDB in the browser and queries a snapshot of the catalogue and cells shipped beside it as Parquet; curves in Observable Plot; published to GitHub Pages by CI on every merge, so there is no server, no credential in the page and no second copy of the truth beyond the snapshot the commit names |
| DCV login node | Scientists use GUI simulation tools | Amazon DCV is the AWS remote-visualisation path; optional here, proves the pattern |

## Build order

Each stage adds one capability from the diagram and ends with a done-signal. Stages 1 to 6 are the core; 7 and 8 are what make it a platform rather than a sweep that happened to run on AWS.

1. **Define the unit of work.** Refactor the sweep so one call is one cell, parameters from the CLI, output a Parquet file named by its cell. Done: runs locally against a local path. Metric: none yet; this fixes the contract.
2. **One node by hand.** A single EC2 instance, packages installed manually, one cell run, result copied to S3. Done: a file lands in S3 and every installed package is written down. Metric: the package list is the input to stage 3.
3. **Freeze the environment.** Build the Apptainer image in CI; rerun stage 2 from a fresh instance using only the image. Done: a bit-identical result. Metric: time-to-reproduce, from weeks of README-following to minutes.
4. **Stand up ParallelCluster.** Commit the cluster YAML: one head node, one Slurm queue, EFS scratch. Submit `srun hostname` across two nodes. Done: nodes appear when a job queues and vanish ten minutes after idle. Metric: time-to-first-node.
5. **Job array for the sweep.** One `sbatch --array` script maps task index to a (d, p) cell and runs the image; results to EFS, synced to S3 on exit. Done: the full grid completes and a logical-error-rate plot comes out. Metric: wall-clock for the sweep versus a laptop.
6. **Scale and cost it.** Rerun at 1, 4, 8 and 16 nodes, each run recording its nodes and timing; price the runs and check the total against Cost Explorer; add a spot queue beside on-demand. Done: a weak-scaling table and a cost-per-sweep figure. Metric: throughput per node and dollars per sweep.
7. **Add tight coupling.** A state-vector simulator sharded across MPI ranks (mpi4py first, C++ second) on an EFA-enabled hpc6a queue. Done: a strong-scaling plot with efficiency falling as nodes rise, and an account of where the time goes. Metric: strong-scaling efficiency at 2, 4, 8 nodes.
8. **Make the cluster a versioned artifact.** First the run record grows to what an audit needs, the image digest, the cluster configuration hash and the Slurm job ids, each cell carries its own start, end and host, and the bucket keeps every object version for a year under S3 Object Lock, so nothing can be silently overwritten or deleted and every run from here on is traceable; these were planned for stage 13 and moved forward because data written under a thin record stays thin. Then CI validates the cluster YAML, builds the image and runs a smoke job on every PR; Terraform owns IAM, S3 and the budget. Done: a node-type change reaches a running cluster through a pull request alone. Metric: changes shipped without SSH.
9. **Graphical node, optional.** A DCV-enabled login node running a GUI tool (ParaView is enough). Done: a remote desktop session opens from a browser. Metric: none; this proves the CAE pattern.
10. **Write it up.** README with the diagram above, the metrics table below and three paragraphs on what broke.
11. **The same simulation on GPUs.** A `g6` queue with GPUs as a Slurm resource, a CUDA image with CuPy and cuQuantum, and the stage 7 simulator with a CUDA gate kernel behind the same kernel interface and an NCCL exchange behind the same exchange protocol, one rank per GPU. cuStateVec runs the same circuit as the vendor reference. Done: the run completes on one GPU, across the four GPUs of one node and the eight of two, and the single-precision GPU state overlaps the double-precision CPU state to within 1e-6. Metric: time per layer and dollars per run against the `hpc6a` node and the laptop, scaling efficiency across GPUs, and the hand-written kernel against cuStateVec.
12. **The decoder loop.** Stim samples labelled syndrome histories as a job array on the sweep queue; a recurrent decoder over syndrome rounds trains on the GPU queue, one GPU at distance 3 and 5 and data-parallel across GPUs where it pays; the trained model becomes a decoder choice in the sweep's cell contract, so evaluation is the stage 5 grid with a decoder axis, at the low noise rates where logical errors are rare and the shot counts are large. One chained run goes from samples to the comparison plot. The architecture is a published one reproduced honestly; the noise models are Stim's depolarising circuit-level noise and a correlated variant where matching is known to be suboptimal. Done: the chain runs without a hand in between. Metric: the learned decoder's logical error rate over PyMatching's with intervals, and what the loop cost.
13. **Results as a versioned artifact.** The run record grows the commit, image digest, cluster configuration hash, Slurm job ids, seeds and parent run ids, so every result is a node in a provenance graph of S3 keys (the digest, configuration hash, job ids and the object lock came in stage 8; seeds and parents arrive with the decoder's runs); a catalogue table collects every record; `compare` joins two runs cell by cell and refuses to call a difference significant when the intervals overlap; a decoder is promoted by a manifest under `models/` changed through a pull request whose checks run the comparison. Done: every figure in the README walks back to its inputs through keys alone. Metric: audit coverage.
14. **A comparison site.** The catalogue and the compare logic get a face: a static site under `web/`, Vite and Svelte in TypeScript, that loads DuckDB's WebAssembly build lazily and queries Parquet shipped beside the page with range requests, so the first paint needs only the shell. The site does three things and no fourth: a reader picks two runs from the catalogue, sees their logical-error-rate curves with intervals cell by cell and the difference where the intervals are apart, and follows each run's provenance chain down to the commit and image digest. Each of the three is finished before the next starts: loading, empty and error states drawn, every control reachable by keyboard and named for a screen reader, colour following the run and never its position, one axis, dark mode from the same tokens, and a test that drives it. A feature that cannot be finished to that bar is left out rather than shipped half done. Playwright drives the comparison end to end in CI, a bundle budget fails the build when the first script grows past it, and CI publishes the site with a fresh data snapshot to GitHub Pages on merge. Done: anyone with the link compares two runs with no server behind the page. Metric: Lighthouse performance on a throttled phone, first paint, query latency, bundle size, merge-to-site time.
15. **A shorter loop and a smaller bill.** First the baseline: a tool that reads the loop time, from a commit's timestamp through the CI run that built its image to the first cell its sweep wrote on the cluster, from records that already exist. Then the changes the earlier stages pointed at, one commit each, measured against it: the grid runs its longest cells first, which is the load imbalance stage 6 found; a pulled image is reused by digest instead of pulled every run; Apptainer and the image are baked into an AMI with `pcluster build-image`, which is most of the seven minutes a node spends configuring; the sweep queue's idle tail shrinks from ten minutes to three, since its cells take seconds; the image is built for arm64 as well and a Graviton queue runs the grid beside `c7a` and `c7i` for cells per dollar, with the stage 3 caveat that Stim's samples are bit-identical only within an architecture; CI caches the environment and skips image builds whose inputs did not change. Done: the same sweep goes from commit to first cell in half the time and costs a third once billed, with a before-and-after plot. Metric: loop time, time to first node, weak-scaling efficiency at 16 nodes, billed cost per sweep, cells per dollar by instance type, CI minutes per pull request.

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
| Own CUDA kernel, cuStateVec as reference | cuStateVec only | The library would be faster to adopt, but the point of the stage is to show where a GPU's time goes, and a kernel one can read is the only way to see it; the library is run beside it so the reader can judge the gap |
| NCCL for the GPU exchange | CUDA-aware MPI | Both move device memory without a host copy; NCCL is what every multi-GPU code uses, needs no particular MPI build, and runs over EFA through the aws-ofi-nccl plugin when a node has one. MPI stays for bootstrap only |
| Single precision on the GPU | Double, as on the CPU | An L4 does double precision at a sixty-fourth of its single rate, which would make the comparison about the card's arithmetic units rather than the simulation; single precision with a measured overlap against the double-precision CPU state is what GPU simulators ship |
| A recurrent decoder over syndrome rounds | A transformer in the AlphaQubit style | The transformer is the published best, and far too large to train honestly on a few GPUs for a portfolio; a recurrent decoder has beaten matching at distance 3 and 5 in the literature, trains in GPU-hours, and the loop around it is the deliverable |
| Evaluate through the sweep's cell contract | A separate evaluation harness | One decoder axis on the existing grid reuses the array, the records, the reducer and the plot, and makes the comparison with matching the same code path for both |
| Own records, DuckDB over S3, static report | MLflow or Weights & Biases | Either tracks experiments well and most data scientists reach for one first; both add a server or an account and a second copy of the truth. The records already exist in S3, DuckDB queries them without a server, and a page built by CI is versioned with the commit that built it |
| Promote a model by pull request | A registry with stages | The registry is a manifest in git pointing at an S3 key and a digest; the audit trail is the PR, which is where this project keeps every other decision |
| Static site with DuckDB in the browser | A small API server over the catalogue | A server is a thing to run, secure and pay for, and would make the comparison depend on the cluster's account being up; the snapshot is a few megabytes of Parquet that the browser queries with range requests, and the page is versioned with the commit that built it |
| Svelte with Vite | React | React is the larger market and either would do; Svelte compiles the components away, so the shell that paints first is a few kilobytes, which is the budget the stage sets out to hit. The React version would be the same site with a bigger first script |
| Observable Plot | Plotly or ECharts | Both are complete and heavy; Plot is a thin grammar over d3 that draws the two chart kinds this site needs, intervals included, in a fraction of the bytes |
| GitHub Pages | S3 and CloudFront | Either serves static files; Pages is one workflow step from the repo that already builds the site, and keeps the public page out of the project that holds the private bucket |
| Measure the loop before changing it | Optimise what looks slow | Stage 6 found the loss was load imbalance and not the scheduler, which nobody would have guessed; a baseline tool turns each later commit into a number rather than a claim |
| Bake an AMI | Keep the configure script | The script was right for stage 4, where a reader can see every step; once it is stable, the seven minutes it costs every node on every run is the largest piece of the loop, and an AMI is a build step in CI like the image |
| Longest cells first | A dynamic work queue | A queue would balance any grid, at the price of a service to run; sorting the grid by expected cost before the array is submitted fixes the imbalance stage 6 measured with one line and no moving parts |
| A shorter idle tail | A warm pool or a minimum node count | Idle nodes cost the same whether they wait before or after a job; with cells that take seconds, three idle minutes cover the gap between back-to-back runs and cut the billed tail by two thirds. A warm node would pay for the hours nobody submits |
| Graviton beside x86 | x86 only | Graviton is around a fifth cheaper per vCPU and most of the sweep's dependencies ship arm64 wheels; the comparison is the cost figure a cloud reader expects, and the architecture caveat on bit-identity from stage 3 stays in the record |
| `g6.12xlarge` | `p4d.24xlarge` | Eight A100s on NVLink with EFA is the proper multi-GPU machine at seven times the price; `g6` answers the single-GPU and PCIe-scaling questions for a few dollars, and the `p4d` point is optional |

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
| GPU speed-up (x) and dollars per run | 11 | Time per layer at thirty qubits on one L4 against one `hpc6a` node and the laptop, each priced at its published rate | reported, with where time goes |
| Multi-GPU scaling efficiency (%) | 11 | T(1) / (N x T(N)) at 2 and 4 GPUs in one node and 8 across two | reported; the two-node point shows what a 40 Gbit/s link does to it |
| GPU state fidelity | 11 | Overlap of the single-precision GPU state with the double-precision CPU state | above 1 - 1e-6 |
| Kernel against cuStateVec (x) | 11 | The hand-written kernel's time per layer over cuStateVec's on the same card | within 2 |
| Learned decoder over matching (ratio) | 12 | Logical error rate ratio at distances 3 and 5, noise rates 1e-3 to 5e-3, 95% intervals from the same shots | below 1 at distance 5 under correlated noise, intervals apart |
| Cost of the loop (USD, GPU-hours, CPU-hours) | 12 | From each chained run's records: generate, train, evaluate | reported |
| Audit coverage (%) | 13 | README figures whose record, digest, commit and inputs resolve through S3 keys alone, over figures reported | 100 |
| Site performance | 14 | Lighthouse performance score on a throttled phone profile; first contentful paint; first script size compressed | 100; under 1 s; under 150 kB |
| Comparison query (ms) | 14 | Two runs joined cell by cell in the browser, median over the catalogue's runs | under 100 |
| Merge-to-site (min) | 14 | Merge on main to a refreshed site with the latest snapshot | under 10 |
| Loop time (min) | 15 | Commit timestamp to the first cell written on the cluster, before and after | halved |
| Time-to-first-node with the AMI (min) | 15 | As stage 4, on the baked image | under 2 |
| Billed cost per sweep at 16 nodes (USD) | 15 | As stage 6, with the shorter idle tail | under 0.10, from 0.30 |
| Cells per dollar by instance type | 15 | The grid on `c7a`, `c7i` and `c8g`, cells over billed dollars | reported |
| CI minutes per pull request | 15 | Sum of job minutes on a docs-only and on a code pull request, before and after | reported |

The two scaling numbers are the ones an HPC reader will look for first; the cost number is the one a cloud reader will. Reporting both is the point of the project.

## Out of scope and guardrails

Out of scope, and said so to keep the README honest:

- Real quantum hardware or hardware-simulation tools such as HFSS or COMSOL; the DCV node proves the pattern with an open-source GUI.
- GPU simulation beyond one node pair; stage 11 covers one `g6` node and two, and leaves NVLink and GPUDirect over EFA to a `p4d` point that is optional.
- Tensor-network simulation; the state vector is the workload throughout.
- Multi-user fairness, accounting or authentication; this is a single-user cluster.
- Real-time decoding; the sweep is batch, and the learned decoder is judged on accuracy and cost, not latency.
- Beating matching above distance 5, or on device data; the decoder stage reproduces a published result and measures it honestly.
- Multi-user experiment tracking; the catalogue and the site serve one team reading one bucket.
- Sign-in on the site; it publishes a snapshot of results that are meant to be public, and the bucket stays private.
- Savings Plans and Reserved Instances; a cluster that scales to zero has no steady state to commit to, and spot is denied by policy.

Cost guardrails, set before stage 2:

- AWS Budget alerts at 20 and 50 USD per month.
- Compute nodes scale to zero after 10 minutes idle; the head node is t3.medium.
- EFS is paid per gigabyte stored, holds only scratch, and is deleted with the cluster.
- Every job carries a cost-allocation tag so nothing is unattributed.
- `pcluster delete-cluster` at the end of every session; a scheduled check confirms nothing is left running.
