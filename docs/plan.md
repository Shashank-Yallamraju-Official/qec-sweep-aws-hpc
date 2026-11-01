# Plan

The design is in [design.md](design.md). This file is the order of work: fifteen stages, each adding one capability and ending with a done-signal, and the commit that delivers each step. A reader of `git log` should be able to follow this list top to bottom.

## Stages

| Stage | Adds | Done when | Metric |
| --- | --- | --- | --- |
| 1 | The unit of work: one call, one cell, one Parquet file | Runs locally against a local path | none; fixes the contract |
| 2 | One node by hand | A file lands in S3 and every installed package is written down | the package list |
| 3 | Frozen environment as an Apptainer image | A bit-identical result from a fresh instance using only the image | time to reproduce, under 10 min: **3.7 min** from launching a fresh Ubuntu node to the identical result in S3, 50 s of which was installing Apptainer, pulling the image and running the cell. Identical holds per CPU architecture: Stim's sampler walks shots in SIMD-width batches, so the same seed gives different samples on an ARM laptop and an x86 node, statistically equivalent but not bit for bit |
| 4 | ParallelCluster with one queue and EFS scratch | Nodes appear when a job queues and vanish ten minutes after idle | time to first node, under 5 min: **4.0 min** from `sbatch` to the first `c7a.large` allocated; both nodes answered `hostname`, and both were terminated 11 min after the job finished. The cluster itself took 10 min to create |
| 5 | Job array for the sweep | The full grid completes and a logical-error-rate plot comes out | sweep wall-clock against a laptop: **7.3 min** on the cluster from `sbatch` to the last of 200 cells written, four nodes from a powered-down queue, against **1.4 min** on a ten-core laptop. Of the cluster's time, 5.1 min was the nodes booting, configuring and pulling the image and 2.2 min was decoding on eight slots; the laptop needed 9.3 CPU-minutes, the cluster 18 slot-minutes. The first measurement, 9.7 min on 2026-10-30, predates the full run record; this one, run 20261101T184309Z, carries it |
| 6 | Scale and cost | A weak-scaling table and a cost-per-sweep figure | cells per node-hour at 1, 4, 7, 8 and 16 nodes, from the first cell written to the last: **1478**, **1325** (90%), **1206** (82%), **1156** (78%), **887** (60%), the last two once the vCPU quota rose to 64; the 90% target holds to 4 nodes and fails at 16. These are the 2026-11-01 runs under the full record, within 4% of the first measurements of 2026-10-30 (1470, 1330, 1210, 1150, 920), which predate it. The loss is load imbalance: the grid runs in distance order, so the forty slowest cells, at d=11, start last, and at 16 nodes the whole grid takes 49 s, not much more than one of them. The figures are from runs whose nodes were all up at the first cell; a 16-node run started while eight of its nodes were still booting measured provisioning instead, 118 cells per node-hour, because Slurm hands tasks to nodes that are still powering up and they wait six minutes for them. Cost per sweep at 7 nodes on demand: **$0.018** while cells ran, **$0.14** once each node's ten idle minutes before scale-down are billed, and at 16 nodes **$0.025** and **$0.30**; at the day's spot price it would be 38% of that, over the one-third target, and this account cannot launch spot at all, an organisation policy denies it. Cost Explorer and the budget both report 0 USD for the month from inside the project, so the check against the bill is open |
| 7 | Tight coupling over MPI on EFA | A strong-scaling plot and an account of where the time goes | strong-scaling efficiency over TCP, provisional: **61%** at 2 nodes, **39%** at 4, **26%** at 8 and **21%** at 16, for 25 qubits and six brickwork layers on `c7a.large` nodes, two ranks per node, 10.3 s on one node and 3.1 s on sixteen. The time goes to the exchanges: a twelfth of it at one node, two fifths at two, three fifths at four, seven tenths at eight and over three quarters at sixteen, while the computing part halves with each doubling as it should, 9.5 s down to 0.9 s. The EFA points were planned on `hpc6a.48xlarge`; the HPC quota request (1,536 vCPUs, lowered to 768) went to manual review and is assumed refused, so they move to `c5n.9xlarge`, 36 vCPUs with 50 Gbit/s EFA from the Standard quota, 32 ranks a node, at 2, 4 and 8 nodes once that quota rises from 64 to 288 vCPUs; the hpc6a queue stays in the configuration for the day its quota lands. Two things broke on the way: each rank runs in its own container and user namespace, so Open MPI's shared-memory single-copy path hangs until it is turned off; and an EFA node carries a second network interface, so the queue needs a private subnet and a NAT gateway |
| 8 | The cluster as a versioned artifact, and complete run records | A node-type change reaches a running cluster through a pull request alone, and every run from here on names the image digest, the cluster configuration and its jobs, in a bucket whose versions cannot be deleted for a year | changes shipped without SSH: every change to the cluster now travels through a pull request. On the pull request, ParallelCluster validates the configuration against the account from a read-only runner (**9 runs** on this stage's own pull request, 3 of them after the workflow was right), the running cluster's head node runs the smoke job through one fixed Systems Manager document and two nodes answer, and Terraform plans. On the merge, the job scripts are installed beside their commit and a changed configuration is applied with the compute fleet stopped around it. The merge of this stage's pull request is the first change shipped that way; each later stage's row carries the count forward. Four things broke: the project's managed policy denies every IAM identity-provider action, so GitHub's OIDC federation is out and the runners are CodeBuild projects carrying roles; GitHub would not let CodeBuild register its own webhooks, which are made once by hand from the endpoint Terraform issues; the dry run needs RunInstances even in dry-run mode, so the two launch validators run only on main; and a dry run that would succeed still exits 1 |
| 9 | Graphical login node (optional) | A remote desktop session opens from a browser | none; proves the pattern |
| 10 | Write-up | A README in every top-level directory, then the root README with the diagram, the metrics table, what broke and the map | |
| 11 | The same simulation on GPUs, optional while the account has no GPU quota | The state-vector run completes on one GPU, then across the GPUs of one node and of two, with the amplitudes matching the CPU run | time per layer and dollars per run on one `g6` GPU against one `hpc6a` node and the laptop; scaling efficiency at 2 and 4 GPUs over PCIe and at 8 across two nodes; the overlap of the single-precision GPU state with the double-precision CPU state, above 1 - 1e-6; the hand-written kernel's time per layer over cuStateVec's, within 2x. Every accelerated quota in the project is zero: the G request for 96 vCPUs was refused on 2026-10-30 and an appeal is open; P, Inf, Trn and DL are zero too. The stage is done last, if at all; the interfaces it plugs into are built without it |
| 12 | The decoder loop: generate, train, evaluate | A learned decoder trained on the cluster decodes cells of the grid beside PyMatching, and one chained run goes from samples to a comparison plot without a hand in between | logical error rate of the learned decoder over PyMatching's at distances 3 and 5, with 95% intervals, under depolarising and under correlated circuit-level noise; below one at distance 5 under correlated noise with the intervals apart is the win; node-hours and dollars to train on `c7a.8xlarge` nodes, the device being a run parameter for the day a GPU queue exists; shots and node-hours to generate and to evaluate |
| 13 | Results as a versioned artifact | Every figure in the README walks back to its run record, image digest, commit and inputs through S3 keys alone; a decoder is promoted by a pull request | audit coverage: **16 of 21** figures in this table resolve through S3 keys alone to a record naming the image digest, the commit, the cluster configuration and the Slurm jobs, 76%. The stage 5, 6 and 7 figures do: stages 5 and 6 were re-measured on 2026-11-01 under the stage 8 record, within 4% of the originals, and stage 7's run already carried it. Four stopwatch timings from stages 3 and 4 resolve to nothing, and one stage 6 figure, the 118 cells per node-hour measured mid-boot, resolves to a record without a digest; stage 15 measures the first kind with records and the second stays as a lesson. Seeds and parents landed with a 16-node run of seed 1 whose parent is the seed-0 run that `models/decoder.json` names: the same seed gives identical error counts in 200 of 200 cells, a different seed changes 187 of them, and the comparison calls none of the 200 different, as intervals that must not touch should when the decoder is the same. The manifest check admits the first entry on its own record from the read-only runner. Changes shipped without SSH: 3 with this stage's pull request. Two things broke: `tee /dev/stderr` fails when a driver running as another user owns the log, so the pull log is copied through a process instead; and compute nodes may put objects but not list them, so a run names its parents explicitly rather than finding the latest |
| 14 | A comparison site | The site does three things, pick two runs, compare them, trace them, and each is finished: loading, empty and error states, keyboard and screen reader, dark mode, a test that drives it, a budget that fails the build. Anyone with the link does all three with no server behind the page, and the site rebuilds with fresh data on every merge | Lighthouse performance on a throttled phone profile (Lighthouse 12, simulated slow 4G and a 4x slower CPU, the production build served locally): **100** on each of four runs, with no render-blocking resource. First contentful paint on that profile: **1.05 to 1.23 s** over the four runs, median 1.2 s, against a target of one second; the page paints from the HTML alone, the stylesheet inlined and the shell written into it, so what remains is the simulated round trips to fetch a 3.2 kB document and the floor the profile sets. The comparison query, two runs joined cell by cell in DuckDB in the browser: **8 to 15 ms**, median **11 ms**, over seven pairs of 200-cell runs from the real bucket and three pairs from the fixture. The first script: **22.6 kB** gzip (20.4 kB brotli) of a 150 kB budget, checked on every build; the query engine (45 kB plus a 184 kB worker and an 8.2 MB WebAssembly module, gzip) and the chart library (89 kB) load after the first paint. The snapshot of the bucket for a publish, 15 runs and 14 sets of cells read in parallel, took 54 s from this machine. Time from merge to a refreshed site, on the first merge that published, PR #14 on 2026-11-01: **1 min 39 s** from the merge commit to the deploy finishing, 60 s of it the snapshot of 17 runs on the read-only runner and 11 s the deploy, against a target of ten minutes; the page and its catalogue answered at the Pages address straight after. Three things broke on the way: a Plot mark given a filtered copy of the data is not faceted and draws in every panel, so every mark now names its facet; Plot lays facets out in one row, so on a phone the panels are placed on a grid of column and row that wraps; and a variable named `state` shadows the `$state` rune in Svelte 5 |
| 15 | A shorter loop and a smaller bill | The same sweep goes from a commit to its first cell in S3 in half the time and the billed sweep costs a third, with each change measured against a baseline taken before any of them | loop time, commit to first cell written on the cluster, before and after; time to first node with a baked AMI, under 2 min from 4.0; weak-scaling efficiency at 16 nodes once the grid runs longest cells first, above 90% from 62%; billed cost per sweep at 16 nodes with a shorter idle tail, under $0.10 from $0.30; cells per dollar on `c7a`, `c7i` and Graviton `c8g`; CI minutes per pull request before and after |

The order of work from stage 8 on is 13, 14, 15, 12, 9, 10; the EFA points of stage 7 when the Standard quota reaches two `c5n.9xlarge` nodes; stage 11 only once a GPU quota exists. No stage after 11 depends on it.

## Commits

### Bootstrap

1. `chore: add licence, gitignore and editor config`
2. `build: add pre-commit with ruff, mypy and commit lint`
3. `build: run the gate per file and guard git from claude code`
4. `ci: lint, type-check and test on every push`
5. `docs: add design document and conventions`
6. `feat(tools): report time and fixes per commit from hook log`

### Stage 1, unit of work

7. `feat(sweep): model a cell as distance, noise rate and shots`
8. `feat(sweep): decode a cell with stim and pymatching`
9. `feat(sweep): write a cell result as parquet named by cell`
10. `feat(sweep): add the sweep command line`
11. `test(sweep): run one cell end to end against a local path`

### Cost guardrails

12. `feat(infra): add terraform for the results bucket`
13. `feat(infra): add budget alerts at 20 and 50 usd a month`
14. `feat(infra): tag every resource for cost allocation`
15. `feat(infra): reap stale instances and email while any run`

### Stage 2, one node by hand

16. `feat(infra): add an instance profile for nodes`
17. `build(image): pin the packages from the hand-built node`
18. `feat(jobs): run one cell on a node and copy the result to s3`

### Docstrings

19. `docs(sweep): add google-style docstrings`
20. `docs(tools): add google-style docstrings`
21. `docs(infra): add google-style docstrings`
22. `build: enforce google-style docstrings with ruff`

### Stage 3, frozen environment

23. `build(image): add apptainer definition from pinned packages`
24. `ci(image): build the image on pull request, publish on main`
25. `test(image): reproduce the hand-built cell from the image`
26. `docs(metrics): record time to reproduce the environment`

### Stage 4, cluster

27. `feat(cluster): add head node, one queue and efs scratch`
28. `feat(cluster): scale compute to zero after ten minutes idle`
29. `feat(jobs): add smoke job running hostname across two nodes`
30. `docs(metrics): record time to first node`

### Stage 5, job array

31. `feat(sweep): map an array task index to a grid cell`
32. `feat(jobs): submit the grid as a slurm array`
33. `feat(jobs): sync results from efs to s3 when the array exits`
34. `feat(sweep): reduce cell results into one table`
35. `feat(sweep): plot logical error rate by distance`
36. `docs(metrics): record sweep wall-clock against a laptop`

### Stage 6, scale and cost

37. `feat(jobs): record each run's nodes and timing for costing`
38. `feat(cluster): add a spot queue beside on-demand`
39. `feat(tools): report cost per sweep from each run's record`
40. `feat(jobs): run the grid at 1, 4, 8 and 16 nodes in turn`
41. `docs(metrics): record weak scaling and cost per sweep`

### Stage 7, tight coupling

42. `feat(mpi): shard a state vector across ranks`
43. `feat(mpi): exchange amplitudes on non-local two-qubit gates`
44. `test(mpi): match sharded amplitudes to a single-rank run`
45. `feat(mpi): run a brickwork circuit and record its timings`
46. `build(image): build an mpi image on the efa stack`
47. `feat(cluster): add an efa-enabled hpc6a queue`
48. `feat(jobs): submit the state-vector run across ranks`
49. `perf(mpi): move the gate kernel to c++`
50. `feat(mpi): plot strong scaling from the run records`
51. `docs(metrics): record strong scaling at 2, 4 and 8 nodes`

### Stage 8, cluster as versioned artifact

52. `feat(sweep): write each cell's start, end and host`
53. `feat(jobs): record image digest, config hash and job ids`
54. `feat(infra): lock the results bucket's versions for a year`
55. `feat(infra): add a deploy role for github actions`
56. `ci(cluster): validate the cluster config on pull request`
57. `ci(cluster): run the smoke job on pull request`
58. `ci(cluster): update the running cluster on merge to main`
59. `ci(infra): plan terraform on pull request, apply on main`
60. `docs(metrics): record changes shipped without ssh`

### Stage 9, graphical node

61. `feat(cluster): add a dcv-enabled login node`
62. `feat(cluster): install paraview on the login node`

### Stage 10, write-up

63. `docs: add a readme to each package`
64. `docs: add readme with architecture, metrics and what broke`

### Stage 11, gpu queue (last, and only with a GPU quota)

65. `feat(cluster): add a g6 queue with gpus as a slurm resource`
66. `feat(jobs): add a smoke job listing every gpu on a node`
67. `build(image): build a cuda image with cupy and cuquantum`
68. `feat(mpi): add a cuda gate kernel on cupy arrays`
69. `feat(mpi): exchange amplitudes between gpus over nccl`
70. `test(mpi): check the gpu run's overlap with the cpu run`
71. `feat(mpi): run the circuit on custatevec as the reference`
72. `feat(jobs): submit the state-vector run across gpus`
73. `feat(mpi): plot time per layer and cost by device`
74. `docs(metrics): record gpu speed-up, scaling and cost per run`
75. `docs: add the gpu path to the readme`

### Stage 12, the decoder loop

76. `feat(decoder): sample labelled syndromes from stim`
77. `feat(jobs): generate the training set as a slurm array`
78. `feat(decoder): add a recurrent decoder over syndrome rounds`
79. `feat(decoder): train on one node and record the run`
80. `feat(decoder): train across nodes with data parallelism`
81. `feat(decoder): decode a cell with the trained model`
82. `feat(sweep): choose the decoder per cell`
83. `feat(jobs): chain generate, train and evaluate as one run`
84. `feat(decoder): plot both decoders' error rates by distance`
85. `docs(metrics): record the learned decoder against matching`

### Stage 13, results as a versioned artifact

86. `feat(jobs): record seeds and parent runs`
87. `feat(results): catalogue every run into one table`
88. `feat(results): compare two runs with confidence intervals`
89. `feat(models): promote a decoder by manifest and pull request`
90. `docs(metrics): record audit coverage of every figure`
91. `docs: add readmes for results, models and the root`

### Stage 14, comparison site

92. `feat(web): scaffold the site with vite and svelte`
93. `feat(web): query the catalogue in the browser with duckdb`
94. `feat(web): pick two runs from the catalogue`
95. `feat(web): compare two runs cell by cell with intervals`
96. `feat(web): draw error-rate curves for the chosen runs`
97. `feat(web): show each run's provenance chain`
98. `feat(web): add dark mode and a keyboard path through it all`
99. `test(web): drive the comparison end to end in playwright`
100. `ci(web): check types, tests and bundle size on pull request`
101. `ci(web): publish the site with its data snapshot on merge`
102. `docs(metrics): record the site's load, query and size`
103. `docs: add the web readme and the site to the root`

### Stage 15, a shorter loop and a smaller bill

104. `feat(tools): time the loop from commit to first cell`
105. `perf(sweep): run the grid longest cells first`
106. `perf(jobs): reuse a pulled image by its digest`
107. `feat(cluster): bake apptainer and the image into an ami`
108. `perf(cluster): shorten the sweep queue's idle tail`
109. `build(image): build the sweep image for arm64 too`
110. `feat(cluster): add a graviton queue beside the x86 one`
111. `feat(jobs): run the grid on each type for cells per dollar`
112. `perf(ci): cache the environment and skip unchanged images`
113. `feat(tools): plot cost and loop time before and after`
114. `docs(metrics): record the loop time and cost per sweep after`
115. `docs: add the optimisation stage to the readme`

Fixes land where they happen as `fix(<scope>): ...`, scoped to the directory they touch, and are the only unplanned commits. Each `docs(metrics)` commit puts a real number into the table in the README and is the last commit of its stage.

## Enforcement

One rulebook, run from three places. `.pre-commit-config.yaml` and `tools/check_commit.py` hold the rules. Git hooks run them at commit time. A Claude Code hook runs them on each file the moment it is written, so a problem surfaces at the edit rather than at the commit. GitHub Actions runs them on every pull request as the backstop, and `main` only accepts pull requests, rebase-merged, with linear history.

- One branch per stage, `stage-NN-<scope>`. Commits follow this list in order.
- A commit message is `<type>(<scope>): <subject>`, the scope being a top-level directory (sweep, mpi, decoder, results, models, web, jobs, cluster, image, infra, tools, metrics, hooks, ci, docs) or omitted for repo-wide changes: first line at most 60 characters, imperative, lowercase, no full stop; body only when the diff cannot say why; no trailers. `tools/check_commit.py` is the rule and the hook runs it.
- Python is checked by ruff with every rule on, including Google-style docstrings on everything public, mypy strict, and pytest. Shell by shellcheck, YAML by yamllint, workflows by actionlint. Terraform by `terraform fmt` and `validate` from the first infra commit.
- Infrastructure is Terraform under `infra/`, state in S3. The state bucket `qec-sweep-tfstate-<account>` is the one resource made by hand, once, with versioning on.
- Process is measured. Claude Code hooks log each edit, test run and commit attempt; `tools/process_report.py` turns the log into active minutes, edits, rejected edits and commit attempts per commit. Each stage's pull request carries its table; the README carries one row per stage.
