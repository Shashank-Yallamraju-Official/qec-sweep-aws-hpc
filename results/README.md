# results

Runs as a versioned artifact. Every run writes its outputs under its own key, `s3://<bucket>/<kind>/<run>/`, beside a `run.json` naming the image URI and the digest it resolved to, the commit the job scripts came from, the hash of the cluster configuration, the Slurm job ids, the seed every cell was given and the runs it was made from. This package reads those records and nothing else.

## Commands

`results-catalogue s3://<bucket>` folds every record in the bucket into one Parquet table at `catalogue/runs.parquet`, one row per run with its address, kind, timings, provenance and cell count. It is a plain file, so any tool that reads Parquet answers questions about the runs without a server:

```sh
duckdb -c "select run, nodes_used, cells, image_digest from 's3://<bucket>/catalogue/runs.parquet' where kind = 'sweeps' order by submitted"
```

`results-compare <run a> <run b>` joins two runs cell by cell, prints each run's provenance, and calls a cell `lower` or `higher` only when the two 95% intervals do not touch; everything else is `within`, whatever the point estimates say. `--out` writes the joined rows as Parquet.

`results-promote <manifest> [--against <manifest>]`, or `--base <directory> <manifest>...`, follows each decoder manifest to its run, refuses one whose digest or noise model the run did not record, reads a learned decoder's weights and refuses a hash the manifest did not say or weights the run was not made from, and judges the candidate against the manifest in force for the same noise model. See [`models/`](../models/README.md).

A directory laid out like the bucket works wherever an address does, which is how the tests run.

## Modules

`store.py` is the bucket or directory, addressed by key. `run.py` is one run's record and its cells. `catalogue.py`, `compare.py` and `manifest.py` are the three commands. Install with `uv sync --extra results`; test with `uv run pytest tests/results`.
