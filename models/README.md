# models

The decoder in force, one manifest per noise model, each changed through a pull request.

`depolarising.json` and `correlated.json` each name a decoder, how a cell is decoded with it, the noise model, the run that evaluated it and the image digest that run must have recorded; a learned decoder adds the address of its weights and their hash. There is one file per noise model because the learned decoder beats matching under correlated noise and loses to it under depolarising: matching is in force under depolarising noise on the 200-cell grid, and the decoder in force under correlated noise is judged on the cells its run names.

Changing a file is a pull request. The `models` workflow follows each manifest to its run in the bucket, refuses one whose digest or noise model the run did not record, reads a learned decoder's weights and refuses a hash the manifest did not say or weights the judged run was not made from, and compares the candidate with the same file on `main` cell by cell, admitting it only if it is worse on no cell with the intervals apart and skipped none. Being better nowhere is allowed: a promotion can be for cost or for speed, as long as it loses no accuracy.

To decode with the decoder in force, copy the weights the manifest names and give them to the cell contract in [sweep](../sweep/README.md):

```sh
aws s3 cp "$(jq -r .artifact models/correlated.json)" decoder.pt
uv run sweep --d 5 --p 0.002 --shots 1000000 --noise correlated --decoder learned --model decoder.pt --out cells
```
