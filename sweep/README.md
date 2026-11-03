# sweep

The unit of work. One call decodes one cell of the surface-code grid, a (distance, noise rate, shots) triple, and writes one Parquet file named by that cell. Everything above this line is platform; everything the platform measures is built from these files.

## Commands

```sh
sweep --d 5 --p 1e-3 --shots 100000 --out cells/           # one cell, by its parameters
sweep --index 42 --out cells/                                 # the same cell by its place in the grid
sweep --d 3 --p 5e-3 --shots 100000 --noise correlated \
      --decoder learned --model decoder.pt --out cells/       # the learned decoder, under the other noise model
sweep-reduce cells/ sweep.parquet                             # every cell file folded into one table
sweep-plot sweep.parquet sweep.png                            # logical error rate against noise, one line per distance
```

A cell file carries the error count, the rate, its 95% Wilson interval, the seed, when and where it was decoded, and which decoder and noise model were used. The same seed gives the same count on the same architecture.

## Modules

`cell.py` is the cell and its name. `noise.py` builds the Stim circuit under either noise model. `decode.py` samples with Stim and decodes with PyMatching. `grid.py` is the sweep grid, 200 cells ordered longest first so a job array's slow tasks start early. `parquet.py` writes and reads a cell file. `reduce.py` and `plot.py` are the two other commands. The learned decoder lives in [`decoder/`](../decoder/README.md) and is reached through `--decoder`.

## Where it fits

[`jobs/`](../jobs/README.md) runs `sweep --index` once per array task inside the image [`image/`](../image/README.md) builds; [`results/`](../results/README.md) reads the files a run leaves behind. Test with `uv run pytest tests/sweep`.
