# Plan

The design is in [design.md](design.md). This file is the order of work: ten stages, each adding one capability and ending with a done-signal, and the commit that delivers each step. A reader of `git log` should be able to follow this list top to bottom.

## Stages

| Stage | Adds | Done when | Metric |
| --- | --- | --- | --- |
| 1 | The unit of work: one call, one cell, one Parquet file | Runs locally against a local path | none; fixes the contract |
| 2 | One node by hand | A file lands in S3 and every installed package is written down | the package list |
| 3 | Frozen environment as an Apptainer image | A bit-identical result from a fresh instance using only the image | time to reproduce, under 10 min: **3.7 min** from launching a fresh Ubuntu node to the identical result in S3, 50 s of which was installing Apptainer, pulling the image and running the cell. Identical holds per CPU architecture: Stim's sampler walks shots in SIMD-width batches, so the same seed gives different samples on an ARM laptop and an x86 node, statistically equivalent but not bit for bit |
| 4 | ParallelCluster with one queue and EFS scratch | Nodes appear when a job queues and vanish ten minutes after idle | time to first node, under 5 min: **4.0 min** from `sbatch` to the first `c7a.large` allocated; both nodes answered `hostname`, and both were terminated 11 min after the job finished. The cluster itself took 10 min to create |
| 5 | Job array for the sweep | The full grid completes and a logical-error-rate plot comes out | sweep wall-clock against a laptop: **9.7 min** on the cluster from `sbatch` to the last of 200 cells written, against **1.4 min** on a ten-core laptop. Of the cluster's time, 7.5 min was four nodes booting and configuring and 2.2 min was decoding on eight slots; the laptop needed 9.3 CPU-minutes, the cluster 18 slot-minutes |
| 6 | Scale and cost | A weak-scaling table and a cost-per-sweep figure | cells per node-hour at 1, 4 and 7 nodes, from the first cell written to the last: **1470**, **1330** (91%), **1210** (82%); 8 and 16 nodes wait on the vCPU quota request, still open. The loss is load imbalance: the grid runs in distance order, so the forty slowest cells, at d=11, start last. Cost per sweep at 7 nodes on demand: **$0.018** while cells ran, **$0.14** once each node's ten idle minutes before scale-down are billed; at the day's spot price it would be 38% of that, over the one-third target, and this account cannot launch spot at all, an organisation policy denies it. Cost Explorer and the budget both report 0 USD for the month from inside the project, so the check against the bill is open |
| 7 | Tight coupling over MPI on EFA | A strong-scaling plot and an account of where the time goes | strong-scaling efficiency at 2, 4, 8 nodes |
| 8 | The cluster as a versioned artifact | A node-type change reaches a running cluster through a pull request alone | changes shipped without SSH |
| 9 | Graphical login node (optional) | A remote desktop session opens from a browser | none; proves the pattern |
| 10 | Write-up | README with the diagram, the metrics table and what broke | |

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
45. `feat(mpi): run a brickwork circuit and record where time goes`
46. `build(image): build an mpi image on the efa stack`
47. `feat(cluster): add an efa-enabled hpc7a queue`
48. `feat(jobs): submit the state-vector run across ranks`
49. `perf(mpi): move the gate kernel to c++`
50. `docs(metrics): record strong scaling at 2, 4 and 8 nodes`

### Stage 8, cluster as versioned artifact

51. `ci(cluster): validate the cluster config on pull request`
52. `ci(cluster): run the smoke job on pull request`
53. `ci(cluster): update the running cluster on merge to main`
54. `ci(infra): plan terraform on pull request, apply on main`
55. `docs(metrics): record changes shipped without ssh`

### Stage 9, graphical node

56. `feat(cluster): add a dcv-enabled login node`
57. `feat(cluster): install paraview on the login node`

### Stage 10, write-up

58. `docs: add readme with architecture, metrics and what broke`

Fixes land where they happen as `fix(<scope>): ...`, scoped to the directory they touch, and are the only unplanned commits. Each `docs(metrics)` commit puts a real number into the table in the README and is the last commit of its stage.

## Enforcement

One rulebook, run from three places. `.pre-commit-config.yaml` and `tools/check_commit.py` hold the rules. Git hooks run them at commit time. A Claude Code hook runs them on each file the moment it is written, so a problem surfaces at the edit rather than at the commit. GitHub Actions runs them on every pull request as the backstop, and `main` only accepts pull requests, rebase-merged, with linear history.

- One branch per stage, `stage-NN-<scope>`. Commits follow this list in order.
- A commit message is `<type>(<scope>): <subject>`, the scope being a top-level directory (sweep, mpi, jobs, cluster, image, infra, tools, metrics, hooks, ci, docs) or omitted for repo-wide changes: first line at most 60 characters, imperative, lowercase, no full stop; body only when the diff cannot say why; no trailers. `tools/check_commit.py` is the rule and the hook runs it.
- Python is checked by ruff with every rule on, including Google-style docstrings on everything public, mypy strict, and pytest. Shell by shellcheck, YAML by yamllint, workflows by actionlint. Terraform by `terraform fmt` and `validate` from the first infra commit.
- Infrastructure is Terraform under `infra/`, state in S3. The state bucket `qec-sweep-tfstate-<account>` is the one resource made by hand, once, with versioning on.
- Process is measured. Claude Code hooks log each edit, test run and commit attempt; `tools/process_report.py` turns the log into active minutes, edits, rejected edits and commit attempts per commit. Each stage's pull request carries its table; the README carries one row per stage.
