# Plan

The design is in [design.md](design.md). This file is the order of work: ten stages, each adding one capability and ending with a done-signal, and the commit that delivers each step. A reader of `git log` should be able to follow this list top to bottom.

## Stages

| Stage | Adds | Done when | Metric |
| --- | --- | --- | --- |
| 1 | The unit of work: one call, one cell, one Parquet file | Runs locally against a local path | none; fixes the contract |
| 2 | One node by hand | A file lands in S3 and every installed package is written down | the package list |
| 3 | Frozen environment as an Apptainer image | A bit-identical result from a fresh instance using only the image | time to reproduce, under 10 min |
| 4 | ParallelCluster with one queue and FSx scratch | Nodes appear when a job queues and vanish ten minutes after idle | time to first node, under 5 min |
| 5 | Job array for the sweep | The full grid completes and a logical-error-rate plot comes out | sweep wall-clock against a laptop |
| 6 | Scale and cost | A weak-scaling table and a cost-per-sweep figure | throughput per node; dollars per sweep |
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

### Stage 2, one node by hand

15. `build(image): pin the packages from the hand-built node`
16. `feat(jobs): run one cell on a node and copy the result to s3`

### Stage 3, frozen environment

17. `build(image): add apptainer definition from pinned packages`
18. `ci(image): build the image on pull request, publish on main`
19. `test(image): reproduce the hand-built cell from the image`
20. `docs(metrics): record time to reproduce the environment`

### Stage 4, cluster

21. `feat(cluster): add head node, one queue and fsx scratch`
22. `feat(cluster): scale compute to zero after ten minutes idle`
23. `feat(jobs): add smoke job running hostname across two nodes`
24. `docs(metrics): record time to first node`

### Stage 5, job array

25. `feat(sweep): map an array task index to a grid cell`
26. `feat(jobs): submit the grid as a slurm array`
27. `feat(jobs): sync results from fsx to s3 when the array exits`
28. `feat(sweep): reduce cell results into one table`
29. `feat(sweep): plot logical error rate by distance`
30. `docs(metrics): record sweep wall-clock against a laptop`

### Stage 6, scale and cost

31. `feat(jobs): tag every job for cost allocation`
32. `feat(cluster): add a spot queue beside on-demand`
33. `feat(tools): report cost per sweep from cost explorer by tag`
34. `docs(metrics): record weak scaling and cost per sweep`

### Stage 7, tight coupling

35. `feat(mpi): shard a state vector across ranks`
36. `feat(mpi): exchange amplitudes on non-local two-qubit gates`
37. `test(mpi): match sharded amplitudes to a single-rank run`
38. `feat(cluster): add an efa-enabled hpc7a queue`
39. `feat(jobs): submit the state-vector run across ranks`
40. `perf(mpi): move the gate kernel to c++`
41. `docs(metrics): record strong scaling at 2, 4 and 8 nodes`

### Stage 8, cluster as versioned artifact

42. `ci(cluster): validate the cluster config on pull request`
43. `ci(cluster): run the smoke job on pull request`
44. `ci(cluster): update the running cluster on merge to main`
45. `ci(infra): plan terraform on pull request, apply on main`
46. `docs(metrics): record changes shipped without ssh`

### Stage 9, graphical node

47. `feat(cluster): add a dcv-enabled login node`
48. `feat(cluster): install paraview on the login node`

### Stage 10, write-up

49. `docs: add readme with architecture, metrics and what broke`

Fixes land where they happen as `fix(<scope>): ...` and are the only unplanned commits. Each `docs(metrics)` commit puts a real number into the table in the README and is the last commit of its stage.

## Enforcement

One rulebook, run from three places. `.pre-commit-config.yaml` and `tools/check_commit.py` hold the rules. Git hooks run them at commit time. A Claude Code hook runs them on each file the moment it is written, so a problem surfaces at the edit rather than at the commit. GitHub Actions runs them on every pull request as the backstop, and `main` only accepts pull requests, rebase-merged, with linear history.

- One branch per stage, `stage-NN-<scope>`. Commits follow this list in order.
- A commit message is `<type>(<scope>): <subject>`: first line at most 60 characters, imperative, lowercase, no full stop; body only when the diff cannot say why; no trailers. `tools/check_commit.py` is the rule and the hook runs it.
- Python is checked by ruff with every rule on, mypy strict, and pytest. Shell by shellcheck, YAML by yamllint, workflows by actionlint. Terraform by `terraform fmt` and `validate` from the first infra commit.
- Process is measured. Claude Code hooks log each edit, test run and commit attempt; `tools/process_report.py` turns the log into active minutes, edits, rejected edits and commit attempts per commit. Each stage's pull request carries its table; the README carries one row per stage.
