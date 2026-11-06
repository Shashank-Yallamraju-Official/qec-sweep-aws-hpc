# experiments

The research loop, written down. One record per experiment, numbered, from [the template](TEMPLATE.md); and this file, the process the records follow. The index reads top to bottom as the questions asked and the decisions taken; the revisions table at the foot says how the method changed and which experiment made it change.

<!-- index -->
| Experiment | Title | Status | Outcome | Cost (USD) | Next |
| --- | --- | --- | --- | --- | --- |
| [01](01-learning-curve.md) | Learning curve of the recurrent decoder at distance 5 | closed | supported | 1.48 | - |
| [02](02-replication.md) | Does the 5,000,000-shot result hold? A second seed and the depolarising control | closed | inconclusive | 1.15 | - |
<!-- /index -->

## The loop

Each step fills one section of the record, in this order, and names the evidence it rests on.

1. **Question.** One sentence, in a form a result can answer.
2. **State.** Where things stand, from records. `uv run experiment baseline` names the decoder in force under each noise model and the chain behind it; `decoder-diagnose` on that chain, pasted as it prints with the command above it, is the State. Per cell the floor, matching and the learned decoder; per training whether it had finished learning; per cell whether the model trained at its noise rate.
3. **Diagnosis.** The causes the State supports, each pointing at the number that supports it. A cause without a number is marked as a guess.
4. **Candidates.** The changes considered, three at least, each with the change, its predicted effect, its cost in node-hours and dollars, and what it would teach whichever way it went. Ranked.
5. **Decision.** The candidate chosen, by the researcher; why; one line each on why not the others.
6. **Prediction.** Before anything runs: the metric, the cells, shots and seeds, the threshold that counts as success, what each outcome would mean, and the compute budget. A threshold or band is derived from a number already in the State, named beside it; a band set by intuition is a guess and is marked as one. A prediction that claims a win over matching names a second training seed, and is `supported` only when both seeds meet the threshold. The record is then committed as `docs(experiments): register ...`, and the Prediction does not change after that commit.
7. **Run.** What ran: the branch's commits, the chain ids in the bucket, the image digests. The `commits` and `runs` fields carry the same.
8. **Result.** The numbers measured, with intervals, against the Prediction: `decoder-diagnose` on the new chains, `tools.cost_report` on their children, run before the cluster is deleted and after `aws login` has been refreshed, since a session that has run long enough to finish a chain has usually outlived its credentials. `outcome` is `supported`, `refuted` or `inconclusive`; `cost_usd` is what the run billed.
9. **Next.** The question that follows, and any change this experiment showed the process needs. The record is committed as `docs(experiments): close ...` with status `closed`; a changed process gets a row below.
10. **Promote.** If the Result beats the decoder in force on its cells with the intervals apart, on both seeds, the manifest for that noise model under [`models/`](../models/README.md) changes on a branch `promote-<slug>`, in a pull request of its own that the `models` workflow judges; the record's Next names it. Otherwise the manifest stands, and Next says so.

## Rules

- One experiment open at a time, on a branch `exp-NN-<slug>`; the record is its plan.
- The researcher decides. The agent diagnoses, ranks and recommends.
- A closed record is never edited. A correction is a new experiment that the old one names in `next`.
- Every number resolves to a run id or to a command. None is typed in.
- The decoder in force changes only through a promotion pull request the check admits; an experiment never edits a manifest.
- The process changes only through a revision row naming the experiment that prompted it, and every record names the version it followed.

## Commands

```sh
uv run experiment new <slug>                        # the next record, from the template
uv run experiment baseline                          # the decoder in force, and its chain
uv run decoder-diagnose s3://bucket/chains/<run>    # the State, from that chain
uv run experiment index                             # rewrite the index above
uv run experiment check                             # what the commit hook refuses otherwise
```

## Where it fits

The records rest on the run records in the bucket, read through [results](../results/README.md), on the chain in [jobs](../jobs/README.md), and on the manifests in [models](../models/README.md), where the loop starts and ends. The loop is stage 16 of [the design](../docs/design.md), closed at the manifest by stage 18. Test the tool with `uv run pytest tests/tools/test_experiment.py`.

## Revisions

| Version | Date | Change | Prompted by |
| --- | --- | --- | --- |
| 1 | 2026-11-03 | The loop as first written | stage 16 |
| 2 | 2026-11-04 | A Prediction that claims a win names a second training seed, and the outcome is `supported` only when both seeds meet the threshold. The close step prices the run before the cluster is deleted, with the session's credentials refreshed first | 01 |
| 3 | 2026-11-06 | A predicted band or threshold is derived from a number already in the State, and the Prediction names that number beside it | 02 |
| 4 | 2026-11-06 | The State starts from the decoder in force, named with its chain by `uv run experiment baseline`, and the loop ends with a Promote step: a Result that beats it on its cells on both seeds is followed by a promotion pull request, and the manifest otherwise stands | 02's Next, stage 18 |
