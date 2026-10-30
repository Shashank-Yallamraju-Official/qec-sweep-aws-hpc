# Plan

The design is in [design.md](design.md). This file is the order of work: fifteen stages, each adding one capability and ending with a done-signal, and the commit that delivers each step. A reader of `git log` should be able to follow this list top to bottom.

## Stages

| Stage | Adds | Done when | Metric |
| --- | --- | --- | --- |
| 1 | The unit of work: one call, one cell, one Parquet file | Runs locally against a local path | none; fixes the contract |
| 2 | One node by hand | A file lands in S3 and every installed package is written down | the package list |
| 3 | Frozen environment as an Apptainer image | A bit-identical result from a fresh instance using only the image | time to reproduce, under 10 min: **3.7 min** from launching a fresh Ubuntu node to the identical result in S3, 50 s of which was installing Apptainer, pulling the image and running the cell. Identical holds per CPU architecture: Stim's sampler walks shots in SIMD-width batches, so the same seed gives different samples on an ARM laptop and an x86 node, statistically equivalent but not bit for bit |
| 4 | ParallelCluster with one queue and EFS scratch | Nodes appear when a job queues and vanish ten minutes after idle | time to first node, under 5 min: **4.0 min** from `sbatch` to the first `c7a.large` allocated; both nodes answered `hostname`, and both were terminated 11 min after the job finished. The cluster itself took 10 min to create |
| 5 | Job array for the sweep | The full grid completes and a logical-error-rate plot comes out | sweep wall-clock against a laptop: **9.7 min** on the cluster from `sbatch` to the last of 200 cells written, against **1.4 min** on a ten-core laptop. Of the cluster's time, 7.5 min was four nodes booting and configuring and 2.2 min was decoding on eight slots; the laptop needed 9.3 CPU-minutes, the cluster 18 slot-minutes |
| 6 | Scale and cost | A weak-scaling table and a cost-per-sweep figure | cells per node-hour at 1, 4, 7, 8 and 16 nodes, from the first cell written to the last: **1470**, **1330** (91%), **1210** (82%), **1150** (78%), **920** (62%), the last two once the vCPU quota rose to 64; the 90% target holds to 4 nodes and fails at 16. The loss is load imbalance: the grid runs in distance order, so the forty slowest cells, at d=11, start last, and at 16 nodes the whole grid takes 49 s, not much more than one of them. The figures are from runs whose nodes were all up at the first cell; a 16-node run started while eight of its nodes were still booting measured provisioning instead, 118 cells per node-hour, because Slurm hands tasks to nodes that are still powering up and they wait six minutes for them. Cost per sweep at 7 nodes on demand: **$0.018** while cells ran, **$0.14** once each node's ten idle minutes before scale-down are billed, and at 16 nodes **$0.024** and **$0.30**; at the day's spot price it would be 38% of that, over the one-third target, and this account cannot launch spot at all, an organisation policy denies it. Cost Explorer and the budget both report 0 USD for the month from inside the project, so the check against the bill is open |
| 7 | Tight coupling over MPI on EFA | A strong-scaling plot and an account of where the time goes | strong-scaling efficiency, provisional: **62%** at 2 nodes and **39%** at 4, for 25 qubits and six brickwork layers on `c7a.large` pairs over TCP, two ranks per node, 10.4 s on one node. The time goes to the exchanges: a tenth of it at one node, two fifths at two, three fifths at four, while the computing part halves each time as it should. The EFA points at 2, 4 and 8 `hpc6a.48xlarge` nodes wait on the account's HPC instance quota, zero until a request for 1,536 vCPUs is granted. Two things broke on the way: each rank runs in its own container and user namespace, so Open MPI's shared-memory single-copy path hangs until it is turned off; and an EFA node carries a second network interface, so the queue needs a private subnet and a NAT gateway |
| 8 | The cluster as a versioned artifact, and complete run records | A node-type change reaches a running cluster through a pull request alone, and every run from here on names the image digest, the cluster configuration and its jobs | changes shipped without SSH |
| 9 | Graphical login node (optional) | A remote desktop session opens from a browser | none; proves the pattern |
| 10 | Write-up | README with the diagram, the metrics table and what broke | |
| 11 | The same simulation on GPUs | The state-vector run completes on one GPU, then across the GPUs of one node and of two, with the amplitudes matching the CPU run | time per layer and dollars per run on one `g6` GPU against one `hpc6a` node and the laptop; scaling efficiency at 2 and 4 GPUs over PCIe and at 8 across two nodes; the overlap of the single-precision GPU state with the double-precision CPU state, above 1 - 1e-6; the hand-written kernel's time per layer over cuStateVec's, within 2x. The G-instance quota starts at zero like the HPC one; the request goes in before the stage starts |
| 12 | The decoder loop: generate, train, evaluate | A learned decoder trained on the cluster decodes cells of the grid beside PyMatching, and one chained run goes from samples to a comparison plot without a hand in between | logical error rate of the learned decoder over PyMatching's at distances 3 and 5, with 95% intervals, under depolarising and under correlated circuit-level noise; below one at distance 5 under correlated noise with the intervals apart is the win; GPU-hours and dollars to train; shots and CPU-hours to generate and to evaluate |
| 13 | Results as a versioned artifact | Every figure in the README walks back to its run record, image digest, commit and inputs through S3 keys alone; a decoder is promoted by a pull request | audit coverage: figures with a complete provenance chain over figures reported, all of them |
| 14 | A comparison site | The site does three things, pick two runs, compare them, trace them, and each is finished: loading, empty and error states, keyboard and screen reader, dark mode, a test that drives it, a budget that fails the build. Anyone with the link does all three with no server behind the page, and the site rebuilds with fresh data on every merge | Lighthouse performance on a throttled phone profile, 100; first paint under one second; the comparison query under 100 ms in the browser; the first script under 150 kB compressed, the query engine loading after it; time from merge to a refreshed site, under ten minutes |
| 15 | A shorter loop and a smaller bill | The same sweep goes from a commit to its first cell in S3 in half the time and the billed sweep costs a third, with each change measured against a baseline taken before any of them | loop time, commit to first cell written on the cluster, before and after; time to first node with a baked AMI, under 2 min from 4.0; weak-scaling efficiency at 16 nodes once the grid runs longest cells first, above 90% from 62%; billed cost per sweep at 16 nodes with a shorter idle tail, under $0.10 from $0.30; cells per dollar on `c7a`, `c7i` and Graviton `c8g`; CI minutes per pull request before and after |

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

52. `feat(sweep): write each cell's start, end and host in its row`
53. `feat(jobs): record image digest, config hash and job ids`
54. `feat(infra): lock the results prefix against overwrites`
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

63. `docs: add readme with architecture, metrics and what broke`

### Stage 11, gpu queue

64. `feat(cluster): add a g6 queue with gpus as a slurm resource`
65. `feat(jobs): add a smoke job listing every gpu on a node`
66. `build(image): build a cuda image with cupy and cuquantum`
67. `feat(mpi): add a cuda gate kernel on cupy arrays`
68. `feat(mpi): exchange amplitudes between gpus over nccl`
69. `test(mpi): check the gpu run's overlap with the cpu run`
70. `feat(mpi): run the circuit on custatevec as the reference`
71. `feat(jobs): submit the state-vector run across gpus`
72. `feat(mpi): plot time per layer and cost by device`
73. `docs(metrics): record gpu speed-up, scaling and cost per run`
74. `docs: add the gpu path to the readme`

### Stage 12, the decoder loop

75. `feat(decoder): sample labelled syndromes from stim`
76. `feat(jobs): generate the training set as a slurm array`
77. `feat(decoder): add a recurrent decoder over syndrome rounds`
78. `feat(decoder): train on one gpu and record the run`
79. `feat(decoder): train across gpus with data parallelism`
80. `feat(decoder): decode a cell with the trained model`
81. `feat(sweep): choose the decoder per cell`
82. `feat(jobs): chain generate, train and evaluate as one run`
83. `feat(decoder): plot both decoders' error rates by distance`
84. `docs(metrics): record the learned decoder against matching`

### Stage 13, results as a versioned artifact

85. `feat(jobs): record seeds and parent runs`
86. `feat(results): catalogue every run into one table`
87. `feat(results): compare two runs with confidence intervals`
88. `feat(models): promote a decoder by manifest and pull request`
89. `docs(metrics): record audit coverage of every figure`
90. `docs: add the loop and the catalogue to the readme`

### Stage 14, comparison site

91. `feat(web): scaffold the site with vite and svelte`
92. `feat(web): query the catalogue in the browser with duckdb`
93. `feat(web): pick two runs from the catalogue`
94. `feat(web): compare two runs cell by cell with intervals`
95. `feat(web): draw error-rate curves for the chosen runs`
96. `feat(web): show each run's provenance chain`
97. `feat(web): add dark mode and a keyboard path through it all`
98. `test(web): drive the comparison end to end in playwright`
99. `ci(web): check types, tests and bundle size on pull request`
100. `ci(web): publish the site with its data snapshot on merge`
101. `docs(metrics): record the site's load, query and size`
102. `docs: add the comparison site to the readme`

### Stage 15, a shorter loop and a smaller bill

103. `feat(tools): time the loop from commit to first cell`
104. `perf(sweep): run the grid longest cells first`
105. `perf(jobs): reuse a pulled image by its digest`
106. `feat(cluster): bake apptainer and the image into an ami`
107. `perf(cluster): shorten the sweep queue's idle tail`
108. `build(image): build the sweep image for arm64 too`
109. `feat(cluster): add a graviton queue beside the x86 one`
110. `feat(jobs): run the grid on each type for cells per dollar`
111. `perf(ci): cache the environment and skip unchanged images`
112. `feat(tools): plot cost and loop time before and after`
113. `docs(metrics): record the loop time and cost per sweep after`
114. `docs: add the optimisation stage to the readme`

Fixes land where they happen as `fix(<scope>): ...`, scoped to the directory they touch, and are the only unplanned commits. Each `docs(metrics)` commit puts a real number into the table in the README and is the last commit of its stage.

## Enforcement

One rulebook, run from three places. `.pre-commit-config.yaml` and `tools/check_commit.py` hold the rules. Git hooks run them at commit time. A Claude Code hook runs them on each file the moment it is written, so a problem surfaces at the edit rather than at the commit. GitHub Actions runs them on every pull request as the backstop, and `main` only accepts pull requests, rebase-merged, with linear history.

- One branch per stage, `stage-NN-<scope>`. Commits follow this list in order.
- A commit message is `<type>(<scope>): <subject>`, the scope being a top-level directory (sweep, mpi, decoder, results, models, web, jobs, cluster, image, infra, tools, metrics, hooks, ci, docs) or omitted for repo-wide changes: first line at most 60 characters, imperative, lowercase, no full stop; body only when the diff cannot say why; no trailers. `tools/check_commit.py` is the rule and the hook runs it.
- Python is checked by ruff with every rule on, including Google-style docstrings on everything public, mypy strict, and pytest. Shell by shellcheck, YAML by yamllint, workflows by actionlint. Terraform by `terraform fmt` and `validate` from the first infra commit.
- Infrastructure is Terraform under `infra/`, state in S3. The state bucket `qec-sweep-tfstate-<account>` is the one resource made by hand, once, with versioning on.
- Process is measured. Claude Code hooks log each edit, test run and commit attempt; `tools/process_report.py` turns the log into active minutes, edits, rejected edits and commit attempts per commit. Each stage's pull request carries its table; the README carries one row per stage.
