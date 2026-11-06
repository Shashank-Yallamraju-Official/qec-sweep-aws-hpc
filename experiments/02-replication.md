---
id: 2
title: Does the 5,000,000-shot result hold? A second seed and the depolarising control
status: registered
process: 2
runs: [chains/20261104T023950Z]
commits: []
pull_request: null
cost_usd: null
outcome: null
next: null
---

## Question

Does experiment 01's win hold? Two parts, as its Next asked. First, the same training on 5,000,000 shots with a second seed: is the 5,000,000-shot decoder below matching at distance 5 under correlated noise again, with the intervals apart, or was one seed lucky? Second, the same 5,000,000-shot training under depolarising noise, where matching is close to optimal and a learned decoder has less to win: does the ratio fall below one there too, which would mean the gain is not the Y-correlation story the design told but something matching leaves on the table under both models?

## State

From experiment 01's 5,000,000-shot chain, read on 2026-11-06 with the tool as revised after experiment 01, which now judges fit on the held-out curve:

```sh
uv run decoder-diagnose s3://qec-sweep-results-523520772490/chains/20261104T023950Z
```

Chain s3://qec-sweep-results-523520772490/chains/20261104T023950Z, correlated noise, trained at p = 0.005

| training | epochs | best epoch | last loss | drop over last epoch | train acc | held-out acc | fit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| d5_p0.005_s50000 | 26 of 60 | 23 | 0.0464 | -1.3% | 0.9866 | 0.9835 | converged |

| cell | floor (from 100,000 shots at most) | matching | learned | learned / matching | verdict | distribution |
| --- | --- | --- | --- | --- | --- | --- |
| d5_p0.001_s1000000 | 0.0656 | 0.00020 | 0.00011 | 0.54 | lower | off |
| d5_p0.002_s1000000 | 0.1217 | 0.00137 | 0.00093 | 0.68 | lower | off |
| d5_p0.005_s1000000 | 0.2514 | 0.01795 | 0.01624 | 0.90 | lower | on |

Read: s3://qec-sweep-results-523520772490/chains/20261104T023950Z, s3://qec-sweep-results-523520772490/train/20261104T023952Z, s3://qec-sweep-results-523520772490/evaluations/20261104T023953Z, s3://qec-sweep-results-523520772490/evaluations/20261104T023955Z

The other two sizes of the curve are in record 01: ratios 3.05 and 1.60 at p = 0.005. Everything above rests on one training seed, 0, which fixed the data (chunks 0 to 99), the held-out split, the initial weights and the batch order, and one evaluation seed, also 0.

## Diagnosis

Not a fault to find this time but a claim to test. Three observations frame it.

1. **The margin is statistical only in the evaluation, not in the training.** At p = 0.005 the learned rate is 0.01624 against matching's 0.01795 over 1,000,000 shots: the difference is 0.0017 and each interval's half-width 0.00025, so the evaluation's sampling noise cannot undo it. What could is the training: a different initialisation, data order or data could land at a worse minimum. Experiment 01 gives no estimate of that spread, since every size ran one seed; its only hint is that held-out accuracy rose monotonically with size (0.9466, 0.9722, 0.9835) and that training and held-out accuracy sit 0.3% apart at 5,000,000 shots, a model that has fitted the distribution rather than a run.
2. **The noise model is a confound the design built in.** The correlated model turns the per-round data noise into pure Y errors, which matching decodes as two independent flips and so does worse: under depolarising noise at the same cell matching makes 1.36% errors against 1.82% here (record 01's Diagnosis). The design predicted a learned decoder would win on that correlation. But stage 12's under-trained model was as bad under depolarising as under correlated noise (ratios 4.4 and 3.7), so nothing yet says the trained one's gain comes from the correlation rather than from matching leaving something on the table under both models. The depolarising chain is the control that separates the two.
3. **A second seed must move the data too, not only the weights.** `chain.sh -s <seed>` samples chunk k with seed + k and trains and evaluates with the seed itself. A second run with `-s 1` would share 99 of its 100 chunks with the first, shifted by one; its data would be the same shots. The second seed has to be at least 100 apart, so the chunks are seeds 100 to 199 and no shot is shared.

Checked and ruled out, as in 01: the evaluation (1,000,000 shots) and the chunks (50,000) use different shot counts, so Stim's streams differ and no training shot is an evaluation shot, for either seed.

## Candidates

| # | Change | Predicted effect | Cost | Teaches |
| --- | --- | --- | --- | --- |
| 1 | **Second seed and the control.** Two 5,000,000-shot chains: correlated noise with `-s 100`, and depolarising noise with `-s 0`; everything else as in 01 | The correlated run lands near 0.90 at p = 0.005 again, below one with intervals apart; the depolarising run lands nearer one, since matching has less to lose there | two chains, about 7 node-hours of `c7a.large`, $1.10 to $1.30 with the head node | Whether the win survives a change of seed, and whether it is the Y-correlation story or a general one |
| 2 | **Second seed only.** The correlated chain with `-s 100` | As the first half of 1 | one chain, about $0.60 | Robustness only; the control waits |
| 3 | **A spread.** Seeds 100, 200 and 300 under correlated noise | Three more points at 5,000,000 shots, a standard deviation of the ratio | three chains, about $1.80 | How wide the seed-to-seed spread is, which 1 only bounds from two points |
| 4 | **Promote now.** Put the seed-0 model into the stage 13 manifest and skip the replication | The site compares it as the decoder in force | a pull request, no compute | Nothing about whether the result holds; against revision 2 of the process |

Recommended: 1. It is the question record 01 asked, both halves, for about a dollar; 3 is the follow-up if 1 shows the two seeds far apart.

## Decision

Candidate 1, chosen by the researcher on 2026-11-06: the second seed and the control together. Why: they are the two halves of the question record 01 left, and together cost about a dollar. Why not the others: 2 leaves the confound in place for another round; 3 buys a spread before knowing whether even one more seed agrees, and loses the control; 4 would make a one-seed result the decoder in force, which revision 2 of the process forbids.

## Prediction

**Metric.** As in experiment 01: the learned decoder's logical error rate over matching's at d = 5, with both 95% Wilson intervals, at p = 0.005 (the training rate), 0.002 and 0.001, from 1,000,000 evaluation shots per cell; the comparison's verdict, which calls `lower` only with the intervals apart.

**Cells, shots and seeds.** Two chains from the job scripts and images of main at `3acba71`, each 100 chunks of 50,000 shots, 5,000,000 in all, trained on 4 ranks with hidden 64, 2 layers, Adam at 1e-3, batch 256, a tenth held out, until the held-out loss has not improved for 3 epochs, capped at 60:

```sh
chain.sh -n correlated   -s 100 -c 100 -e 60 -P 3 -N 4 -r 0.001 -r 0.002 -r 0.005 <sweep> <train> s3://qec-sweep-results-523520772490 sweep 50000 1000000 5:0.005
chain.sh -n depolarising -s 0   -c 100 -e 60 -P 3 -N 4 -r 0.001 -r 0.002 -r 0.005 <sweep> <train> s3://qec-sweep-results-523520772490 sweep 50000 1000000 5:0.005
```

Seed 100 puts the correlated run's chunks at seeds 100 to 199, its split, weights and batch order at 100 and its evaluation at 100, so it shares no shot and no random draw with experiment 01's seed 0. The depolarising run keeps seed 0 so that it differs from experiment 01's 5,000,000-shot chain in the noise model alone.

**Thresholds.** Two predictions, each held to.

1. *The win holds.* The seed-100 correlated decoder is below matching at p = 0.005 with the intervals apart, and its ratio is within 0.15 of seed 0's 0.90. Fails if the verdict at p = 0.005 is `within` or `higher`.
2. *The gain is the correlation.* Under depolarising noise the ratio at p = 0.005 lies between 0.90 and 1.10: a learned decoder has less to win where matching is near optimal, so it lands near matching, above the correlated ratio. Fails low if the depolarising ratio is below 0.85 with the intervals apart, which would say the gain is general and the design's Y-correlation story is not what is being measured; fails high if it is above 1.10.

**Outcome.** `supported` when both hold; `refuted` when 1 fails, whatever 2 does, since the result would then not hold; `inconclusive` when 1 holds and 2 fails either way, with the Result saying which way and what that means for the story. Under revision 2, prediction 1 holding is what lets experiment 01's win be called supported on two seeds.

**What each outcome means.** Supported: promote the seed-0 model through the stage 13 manifest, and the next question is where the curve flattens (25,000,000 shots). Refuted: the next experiment is a spread of seeds, and nothing is promoted. Inconclusive low: the design's account of why the decoder wins is wrong and the next experiment looks at what matching leaves on the table under depolarising noise; inconclusive high: the depolarising cell needs its own training rate or a bigger model, which is candidate 4 of experiment 01.

**Budget.** Under $3 billed, expected $1.10 to $1.30: two chains of about 3.7 node-hours each on `c7a.large` and `c7i.large`, plus the `t3.medium` head node for about an hour. Priced from the records before the cluster is deleted, in the same session, with `aws login` refreshed first.

## Run

## Result

## Next
