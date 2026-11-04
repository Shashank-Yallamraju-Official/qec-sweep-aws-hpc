---
id: 1
title: Learning curve of the recurrent decoder at distance 5
status: registered
process: 1
runs: [chains/20261103T212407Z]
commits: []
pull_request: null
cost_usd: null
outcome: null
next: null
---

## Question

Is the stage 12 decoder data-limited or capacity-limited? That is: does its error rate at distance 5 fall towards matching's as the training set grows from 200,000 shots to 5,000,000, trained to convergence rather than for ten epochs, or does the curve go flat?

## State

From the last correlated-noise chain of stage 12, read on 2026-11-03:

```sh
uv run decoder-diagnose s3://qec-sweep-results-523520772490/chains/20261103T212407Z
```

Chain s3://qec-sweep-results-523520772490/chains/20261103T212407Z, correlated noise, trained at p = 0.005

| training | epochs | last loss | drop over last epoch | train acc | held-out acc | fit |
| --- | --- | --- | --- | --- | --- | --- |
| d3_p0.005_s50000 | 10 | 0.0614 | 2.6% | 0.9790 | 0.9793 | underfit |
| d5_p0.005_s50000 | 10 | 0.1560 | 3.7% | 0.9386 | 0.9323 | underfit |

| cell | floor | matching | learned | learned / matching | verdict | distribution |
| --- | --- | --- | --- | --- | --- | --- |
| d3_p0.001_s100000 | 0.0258 | 0.00092 | 0.00094 | 1.02 | within | off |
| d3_p0.002_s100000 | 0.0494 | 0.00318 | 0.00338 | 1.06 | within | off |
| d3_p0.005_s100000 | 0.1155 | 0.01945 | 0.02199 | 1.13 | higher | on |
| d5_p0.001_s100000 | 0.0656 | 0.00019 | 0.00240 | 12.63 | higher | off |
| d5_p0.002_s100000 | 0.1217 | 0.00164 | 0.01049 | 6.40 | higher | off |
| d5_p0.005_s100000 | 0.2514 | 0.01820 | 0.06786 | 3.73 | higher | on |

Read: s3://qec-sweep-results-523520772490/chains/20261103T212407Z, s3://qec-sweep-results-523520772490/train/20261103T212409Z, s3://qec-sweep-results-523520772490/train/20261103T212412Z, s3://qec-sweep-results-523520772490/evaluations/20261103T212413Z, s3://qec-sweep-results-523520772490/evaluations/20261103T212414Z

Each training ran ten epochs on 200,000 shots (four files of 50,000) at p = 0.005, two ranks, in 20 to 25 s. The depolarising chain, 20261103T212320Z, tells the same story: d = 5 ratios 10.4, 10.7 and 4.4.

## Diagnosis

Three causes, two with a number behind them and one without.

1. **Training stopped while the loss was still falling.** The d = 5 loss fell 3.7% over its last epoch (0.1620 to 0.1560) and had fallen every epoch; training and held-out accuracy are 0.9386 and 0.9323, so the model is not memorising. Ten epochs on 200,000 shots is 25 s of compute; the published architecture was trained far longer. Underfit, by the State's own verdict.
2. **The model was evaluated at noise rates it never saw.** Trained at p = 0.005 only; at that rate the d = 5 ratio is 3.73, at the two rates it never saw 6.40 and 12.63. Two of the three d = 5 figures measure extrapolation, not decoding.
3. **The model starts from nothing** (a guess, no number). Matching gets the circuit's structure from the detector error model for free; the LSTM has to find it in the data. A learned residual on top of matching would start where matching ends.

Checked and ruled out: a train-test leak through the seed. Training chunk k of a cell is sampled with seed k and the evaluation with seed 0, but at a different shot count, and Stim's sample stream differs with the count (verified: the first 50,000 of a 1,000,000-shot sample with seed 0 are not the 50,000-shot sample with seed 0). The headroom is real but narrow: at d = 5, p = 0.005 matching makes 1.82% errors under correlated noise against 1.36% under depolarising, a third worse, which is what a decoder that sees both stabiliser kinds has to win back.

## Candidates

| # | Change | Predicted effect | Cost | Teaches |
| --- | --- | --- | --- | --- |
| 1 | **Learning curve.** Same model; 200,000, 1,000,000 and 5,000,000 training shots at d = 5, trained until the held-out loss stalls; evaluated at the training rate and below | The ratio at p = 0.005 falls with shots if the model is data-limited; the curve goes flat if it is capacity-limited | ~6 node-hours of `c7a.large`, $1 to $2; two small code changes (early stopping, per-rank loading) | Which of the two limits binds, which decides everything after |
| 2 | **Train in-distribution.** One model per evaluation rate, or one model on shots mixed across the rates | Removes the extrapolation penalty at p = 0.001 and 0.002; ratios there fall towards the p = 0.005 one | ~2 node-hours, under $1; a chain option | How much of the low-rate gap is distribution shift rather than decoding |
| 3 | **Learn the residual on matching.** Input the syndrome and matching's correction; predict whether matching is wrong | The baseline becomes matching; the model has only to learn matching's blind spot, the Y correlation; most likely route to a ratio below one | ~2 node-hours, under $1; a day of code in `decoder/` | Whether matching's loss under correlated noise is learnable at all |
| 4 | **Bigger or different architecture.** 128 or 256 units, three layers, or a two-head read of the final round as the paper did | Lower error only if capacity binds | $1 to $3 | Nothing until candidate 1 has said capacity binds |

Recommended order: 1, then 3 or 4 depending on what 1 says.

## Decision

Candidate 1, the learning curve, chosen by the researcher on 2026-11-03 in approving the stage 16 design, with its parameters picked the same afternoon: correlated noise only, since the stage 12 win criterion is correlated noise at distance 5; 1,000,000 evaluation shots per cell, so that matching's 180 or so errors at p = 0.001 give a readable ratio; a budget under $5.

Why not the others: 2 answers a narrower question and its answer is partly known from the State (two thirds of the low-rate gap vanishes at the training rate); 3 is the most promising route to the win but presumes the architecture can learn at all at d = 5, which 1 tests first; 4 is only worth its cost if 1 says capacity binds.

## Prediction

**Metric.** The learned decoder's logical error rate over matching's at d = 5 under correlated noise, with the 95% Wilson intervals of both, at p = 0.005 (the training rate) and at p = 0.002 and 0.001, for each training-set size.

**Cells, shots and seeds.** Three chains, one per size, each `jobs/chain.sh -n correlated -s 0 -c <chunks> -N 4 -r 0.001 -r 0.002 -r 0.005 ... 50000 1000000 5:0.005` with 4, 20 and 100 chunks of 50,000 shots, so the sets are 200,000, 1,000,000 and 5,000,000 shots and each is a prefix of the next (chunk k has seed k). Training: hidden 64, 2 layers, Adam at 1e-3, batch 256 per rank, 4 ranks, a tenth held out; epochs until the held-out loss has not improved for 3 epochs, capped at 60. Evaluation: d = 5 at the three rates, 1,000,000 shots, seed 0, by matching and by the learned decoder.

**Threshold.** The hypothesis is that the decoder is data-limited. *Supported* if the ratio at p = 0.005 for the 5,000,000-shot model is below half the ratio for the 200,000-shot model, with the two learned intervals apart. *Refuted* if the 5,000,000-shot ratio is not below the 200,000-shot one with the intervals apart. *Inconclusive* otherwise. Second, held to as well: the ratio at p = 0.001 stays above 3 for every size, because that gap is extrapolation, which more data at p = 0.005 does not fix.

**What each outcome means.** Supported: the next experiment buys data or trains in-distribution before touching the architecture. Refuted: the next experiment is candidate 3 or 4. Inconclusive: one more size, or the slope of the curve decides.

**Budget.** Under $5 billed, expected $1 to $2: three chains on `c7a.large` nodes, about six node-hours including boots and idle tails, and the `t3.medium` head node for about two hours.

## Run

## Result

## Next
