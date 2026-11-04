---
id: 1
title: Learning curve of the recurrent decoder at distance 5
status: closed
process: 1
runs: [chains/20261103T212407Z, chains/20261104T023936Z, chains/20261104T023943Z, chains/20261104T023950Z]
commits: [3361f095306723283bf00cf0f14b34c7dc9e6e2a, 9956804f206d6c8bad85f05b9b431aa41966f1ac]
pull_request: null
cost_usd: 1.48
outcome: supported
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

Submitted on 2026-11-04 at 02:39 UTC from the head node of a fresh `qec` cluster, the job scripts installed from commit `9956804` and both images built from it by pull request #23's image workflow (sweep digest `7323f114…`, train digest `82720faf…`, as the chain records name them in full):

```sh
for c in 4 20 100; do
  /opt/qec/jobs/chain.sh -n correlated -s 0 -c $c -e 60 -P 3 -N 4 -r 0.001 -r 0.002 -r 0.005 \
    oras://ghcr.io/shashank-yallamraju-official/qec-sweep-aws-hpc/sweep:9956804f206d6c8bad85f05b9b431aa41966f1ac \
    oras://ghcr.io/shashank-yallamraju-official/qec-sweep-aws-hpc/train:9956804f206d6c8bad85f05b9b431aa41966f1ac \
    s3://qec-sweep-results-523520772490 sweep 50000 1000000 5:0.005
done
```

| Training shots | Chunks | Chain |
| --- | --- | --- |
| 200,000 | 4 | `chains/20261104T023936Z` |
| 1,000,000 | 20 | `chains/20261104T023943Z` |
| 5,000,000 | 100 | `chains/20261104T023950Z` |

The code that ran is the two commits after the registration: early stopping with batched scoring (`feat(decoder): stop training when held-out loss stalls`) and per-rank loading of the sample files (`feat(decoder): load each rank's share of the samples alone`), both listed in `commits` with the registration's successors. The sweep queue filled from both its compute resources, `c7a.large` and `c7i.large`, so the generate arrays ran on a mix of the two.

## Result

Read on 2026-11-04 with `decoder-diagnose` on each chain; the rates are per shot over 1,000,000 evaluation shots, the intervals 95% Wilson from those counts, the verdicts the comparison's, which calls a difference only when the intervals are apart.

| Training shots | p | Matching | Learned | Learned / matching | Verdict |
| --- | --- | --- | --- | --- | --- |
| 200,000 | 0.005 | 0.01795 [0.01769, 0.01821] | 0.05472 [0.05428, 0.05517] | **3.05** | higher |
| 1,000,000 | 0.005 | same | 0.02878 [0.02845, 0.02911] | **1.60** | higher |
| 5,000,000 | 0.005 | same | 0.01624 [0.01599, 0.01649] | **0.90** | lower |
| 200,000 | 0.002 | 0.00137 [0.00130, 0.00144] | 0.00685 [0.00669, 0.00701] | 5.01 | higher |
| 1,000,000 | 0.002 | same | 0.00201 [0.00192, 0.00210] | 1.47 | higher |
| 5,000,000 | 0.002 | same | 0.00093 [0.00087, 0.00099] | **0.68** | lower |
| 200,000 | 0.001 | 0.00020 [0.00017, 0.00023] | 0.00141 [0.00134, 0.00149] | 7.01 | higher |
| 1,000,000 | 0.001 | same | 0.00025 [0.00022, 0.00028] | 1.22 | within |
| 5,000,000 | 0.001 | same | 0.00011 [0.00009, 0.00013] | **0.54** | lower |

Training, from the records (`train/20261104T023938Z`, `…T023945Z` and `…T023952Z`, as the chains name them): the 200,000-shot model stopped by patience after 29 epochs, the 1,000,000-shot one after 32, the 5,000,000-shot one after 26 of the 60 allowed, with held-out accuracy 0.9466, 0.9722 and 0.9835 against training accuracy 0.9537, 0.9809 and 0.9866; none memorised. The 5,000,000-shot training loss had stopped falling (0.6% over its last epoch); the two smaller ones were still falling by about 2% an epoch when their held-out loss stalled.

**Against the Prediction.** The first threshold is met with room: the ratio at p = 0.005 fell from 3.05 to 0.90, a factor of 3.4 against the factor of 2 required, with the learned intervals far apart. The second prediction is **wrong**: the ratio at p = 0.001 did not stay above 3 but fell to 1.22 at 1,000,000 shots and 0.54 at 5,000,000. More data at the training rate fixed the off-distribution cells as well as the in-distribution one; the extrapolation penalty was a symptom of the under-trained model, not a cause of its own.

**Beyond the Prediction.** The 5,000,000-shot model is below matching at every rate with the intervals apart, which is the stage 12 win criterion, met at distance 5 under correlated noise. Over the three sizes the ratio at p = 0.005 falls as shots to the power of about 0.38, halving for every six-fold increase in shots, and had not flattened by 5,000,000.

**Threats.** One training seed, one evaluation seed: the win rests on a single model, and a second seed is owed before it is called more than one experiment's result. The evaluation and training sets share seed 0 at different shot counts; Stim's streams differ with the count (verified before the run), so no shot is in both, but a clean split would use a seed no chunk uses. The `fit` column of `decoder-diagnose` reads the training loss, which with early stopping says "underfit" of a model whose held-out loss had stalled; the tool should read the held-out curve.

**Cost.** Priced from the records at the published on-demand rates (`c7a.large` $0.1026/h, `c7i.large` $0.0893/h, `t3.medium` $0.0416/h on 2026-11-04). The decoder-chain records carry no instance type, since the sweep queue fills from two, so `tools.cost_report` refuses them and the figure is computed the same way by hand: node count times wall-clock from submission to the last write, plus the three-minute idle tail per node, priced at the dearer of the two types as an upper bound. Compute: 5.93 node-hours running, 9.13 billed with tails, **$0.94** at most ($0.12 for the 200,000-shot chain, $0.26 for 1,000,000, $0.56 for 5,000,000). Head node: 12.9 hours, **$0.54**, of which the experiment needed about 1.3; the rest was the cluster waiting overnight for a session whose credentials had expired, a cost of the process, not of the science. Total **$1.48**, under the $5 budget and inside the $1 to $2 expected.

## Next

**The question that follows.** Does the result hold? A second training seed at 5,000,000 shots, and the same curve under depolarising noise, where matching is close to optimal and a learned decoder has less to win: if the ratio falls below one there too, the gain is not the Y-correlation story the design told but something matching leaves on the table under both models. Then: promote the 5,000,000-shot model through the stage 13 manifest so the site compares it, and extend the curve to 25,000,000 shots to see where it flattens.

**The process.** Two changes, both from this experiment: a Prediction that claims a win names a second seed before the outcome is called supported; and `decoder-diagnose` reads the held-out loss curve, not the training loss, for its fit verdict, since training now stops on the former. Revision 2 of the README carries the first; the second is a `fix(decoder)` for the next experiment to make before its State.
