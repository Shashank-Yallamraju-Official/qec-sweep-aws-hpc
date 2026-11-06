---
name: experiment
description: Run one pass of the research loop in experiments/README.md, from the diagnosis of the decoder in force to a closed record and, when it wins, a promotion pull request, stopping at the Decision for the researcher.
---

Follow `experiments/README.md`; it is the process, this file only orders the calls.

1. Read `experiments/README.md` and the latest record under `experiments/`. The Next of the latest closed record is the Question unless the researcher gives another.
2. Branch `exp-NN-<slug>` from main. `uv run experiment new <slug>`.
3. `uv run experiment baseline` names the decoder in force under each noise model and the chain behind it. Run the `decoder-diagnose` command it prints for the noise model in question and paste its output under State, with the command.
4. Write Diagnosis and Candidates as the README says. Stop. Show the candidates to the researcher and ask which one; do not pick.
5. Write Decision and Prediction with their answer. `uv run experiment index`, then commit `docs(experiments): register <slug>`.
6. Implement and run what the Prediction names. Fill Run as it happens.
7. Fill Result from `decoder-diagnose` on the new chains and `tools.cost_report`, set `outcome`, `cost_usd`, `runs`, `commits`; write Next; set `status: closed`. `uv run experiment index`, then commit `docs(experiments): close <slug>`.
8. If Next names a change to the process, add a revision row to the README in the same commit.
9. After the experiment's pull request is merged: if the Result beats the decoder in force on its cells with the intervals apart on both seeds, branch `promote-<slug>` from main, change that noise model's manifest under `models/` (run, image digest, and for a learned decoder the weights' address and sha256), commit `feat(models): ...`, and open the pull request for the `models` workflow to judge. Otherwise do nothing to `models/`.
