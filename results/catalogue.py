"""Every run's record folded into one table: the ``results-catalogue`` command."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import asdict
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from results.run import RECORD, parse_record
from results.store import Store, open_store

CATALOGUE = "catalogue/runs.parquet"

FIELDS: list[pa.Field[Any]] = [
    pa.field("key", pa.string()),
    pa.field("kind", pa.string()),
    pa.field("run", pa.string()),
    pa.field("submitted", pa.timestamp("us", "UTC")),
    pa.field("finished", pa.timestamp("us", "UTC")),
    pa.field("queue", pa.string()),
    pa.field("commit", pa.string()),
    pa.field("image", pa.string()),
    pa.field("image_digest", pa.string()),
    pa.field("cluster_config_sha256", pa.string()),
    pa.field("instance_type", pa.string()),
    pa.field("nodes", pa.int32()),
    pa.field("nodes_used", pa.int32()),
    pa.field("seed", pa.int64()),
    pa.field("parents", pa.list_(pa.string())),
    pa.field("jobs", pa.string()),
    pa.field("parameters", pa.string()),
    pa.field("cells", pa.int32()),
]
SCHEMA = pa.schema(FIELDS)


def catalogue(store: Store) -> pa.Table:
    """One row per run in the store, oldest first.

    A run is a ``run.json`` and whatever sits beside it; its kind is the prefix it
    was written under and its cell count is the Parquet files beside the record.
    One listing of the store finds them all.
    """
    keys = list(store.keys())
    rows = []
    for record_key in (k for k in keys if k.endswith(f"/{RECORD}")):
        run_key = record_key.removesuffix(f"/{RECORD}")
        record = parse_record(
            store.uri(run_key), run_key.split("/", 1)[0], store.read(record_key).decode()
        )
        rows.append({**asdict(record), "cells": _cells_beside(keys, run_key)})
    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    return table.sort_by("submitted")


def _cells_beside(keys: Sequence[str], run_key: str) -> int:
    prefix = f"{run_key}/"
    return sum(
        1
        for k in keys
        if k.startswith(prefix) and k.endswith(".parquet") and "/" not in k.removeprefix(prefix)
    )


def write_catalogue(store: Store, table: pa.Table, key: str = CATALOGUE) -> str:
    """Write the table into the store it describes and return its address."""
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    store.write(key, sink.getvalue().to_pybytes())
    return store.uri(key)


def main(argv: Sequence[str] | None = None) -> int:
    """Catalogue a store's runs into it and print what was found.

    Args:
        argv: ``<store> [--out key]``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when the store holds no run.
    """
    parser = argparse.ArgumentParser(
        prog="results-catalogue", description="fold every run's record into one table"
    )
    parser.add_argument("store", help="s3://bucket or a directory holding runs")
    parser.add_argument("--out", default=CATALOGUE, help="key to write the table at")
    args = parser.parse_args(argv)
    store = open_store(args.store)
    table = catalogue(store)
    if table.num_rows == 0:
        print(f"results-catalogue: no {RECORD} under {args.store}", file=sys.stderr)
        return 2
    print(f"{table.num_rows} runs -> {write_catalogue(store, table, args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
