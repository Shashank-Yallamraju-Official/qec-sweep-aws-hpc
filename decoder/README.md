# decoder

The learned decoder and its loop: labelled syndrome samples, a recurrent model trained on them, the model as a decoder of the sweep's cells, and the plot of both decoders side by side. The architecture is a published one, an LSTM over syndrome rounds, reproduced as written; what the loop measures is how far it gets against PyMatching.

## Commands

```sh
decoder-sample --d 3 --p 5e-3 --shots 50000 --seed 0 --noise correlated --out samples/   # one .npz per call
decoder-train --samples samples/ --out model/ --epochs 10                                 # decoder.pt and train.json
decoder-plot evaluations/matching evaluations/learned --out decoders.png                  # both decoders, by distance
```

Launched once per node with `RANK`, `WORLD_SIZE`, `MASTER_ADDR` and `MASTER_PORT` set, `decoder-train` trains one model across the nodes: each holds a share of the shots and the gradients are averaged every step. The device is a parameter, so the same call moves to a GPU queue the day one exists. A trained model decodes a cell through `sweep --decoder learned --model decoder.pt`, so both decoders are judged by the same records, comparison and plot.

## Modules

`sample.py` arranges Stim's detection events round by round. `model.py` is the LSTM. `train.py` is the training and its record. `evaluate.py` decodes a cell with a saved model. `plot.py` joins two evaluations and draws them.

## Where it fits

[`jobs/chain.sh`](../jobs/README.md) runs the whole loop as one chain of Slurm jobs. Torch is the `decoder` extra, from PyTorch's CPU index: `uv sync --extra decoder`; test with `uv run pytest tests/decoder`. The measured result is in row 12 of [the plan](../docs/plan.md).
