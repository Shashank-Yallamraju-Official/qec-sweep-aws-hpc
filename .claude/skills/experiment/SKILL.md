---
name: experiment
description: Run one pass of the research loop in experiments/README.md, from the last chain's diagnosis to a closed record, stopping at the Decision for the researcher.
---

Follow `experiments/README.md`; it is the process, this file only orders the calls.

1. Read `experiments/README.md` and the latest record under `experiments/`. The Next of the latest closed record is the Question unless the researcher gives another.
2. Branch `exp-NN-<slug>` from main. `uv run experiment new <slug>`.
3. `uv run decoder-diagnose s3://<bucket>/chains/<last chain>` and paste its output under State, with the command.
4. Write Diagnosis and Candidates as the README says. Stop. Show the candidates to the researcher and ask which one; do not pick.
5. Write Decision and Prediction with their answer. `uv run experiment index`, then commit `docs(experiments): register <slug>`.
6. Implement and run what the Prediction names. Fill Run as it happens.
7. Fill Result from `decoder-diagnose` on the new chains and `tools.cost_report`, set `outcome`, `cost_usd`, `runs`, `commits`; write Next; set `status: closed`. `uv run experiment index`, then commit `docs(experiments): close <slug>`.
8. If Next names a change to the process, add a revision row to the README in the same commit.
