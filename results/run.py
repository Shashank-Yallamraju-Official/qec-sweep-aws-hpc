"""One run as its record describes it, and the cells it wrote."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq

from results.store import Store

RECORD = "run.json"


@dataclass(frozen=True)
class RunRecord:
    """What a run recorded about itself, in the shape every kind of run shares.

    Attributes:
        key: The run's full address; its cells and logs live under it.
        kind: The prefix the run was written under: ``sweeps``, ``statevector``.
        run: The run's name, its submission time in UTC.
        submitted: When it was submitted.
        finished: When its last output was written; ``None`` while it is still going.
        queue: The Slurm partition it ran on.
        commit: The commit the job scripts came from, when the deploy workflow installed them.
        image: The image URI it was asked to run.
        image_digest: The digest that URI resolved to, which cannot move.
        cluster_config_sha256: The hash of the cluster configuration it ran under.
        instance_type: The node type.
        nodes: The node count it was pinned to, if any.
        nodes_used: The nodes that actually ran a task.
        seed: The sampler seed every cell was given.
        parents: The runs this one was made from, by full address.
        jobs: The Slurm job ids, as the submitter recorded them, in JSON.
        parameters: Whatever else the record says, in JSON, such as a circuit's size.
    """

    key: str
    kind: str
    run: str
    submitted: datetime
    finished: datetime | None
    queue: str
    commit: str | None
    image: str | None
    image_digest: str | None
    cluster_config_sha256: str | None
    instance_type: str | None
    nodes: int | None
    nodes_used: int | None
    seed: int | None
    parents: tuple[str, ...]
    jobs: str
    parameters: str


NAMED = {f.name for f in fields(RunRecord)}
REQUIRED = {"run", "queue", "submitted"}


def parse_record(key: str, kind: str, text: str) -> RunRecord:
    """Read a ``run.json`` into a record; a field a thinner record lacks is ``None``.

    Raises:
        ValueError: When the record lacks a field every run writes.
    """
    raw = json.loads(text)
    if missing := REQUIRED - raw.keys():
        msg = f"{key} record lacks {', '.join(sorted(missing))}"
        raise ValueError(msg)
    finished = raw.get("finished")
    return RunRecord(
        key=key,
        kind=kind,
        run=raw["run"],
        submitted=datetime.fromisoformat(raw["submitted"]),
        finished=datetime.fromisoformat(finished) if finished else None,
        queue=raw["queue"],
        commit=raw.get("commit"),
        image=raw.get("image"),
        image_digest=raw.get("image_digest"),
        cluster_config_sha256=raw.get("cluster_config_sha256"),
        instance_type=raw.get("instance_type"),
        nodes=raw.get("nodes"),
        nodes_used=raw.get("nodes_used"),
        seed=raw.get("seed"),
        parents=tuple(raw.get("parents", ())),
        jobs=json.dumps(raw.get("jobs", {}), sort_keys=True),
        parameters=json.dumps({k: v for k, v in raw.items() if k not in NAMED}, sort_keys=True),
    )


def read_record(store: Store, key: str) -> RunRecord:
    """The record of the run at a key; its kind is the key's first segment."""
    kind = key.split("/", 1)[0]
    return parse_record(store.uri(key), kind, store.read(f"{key}/{RECORD}").decode())


def is_cell(key: str, run_key: str) -> bool:
    """Whether a key is a cell of the run: a Parquet file right beside its record."""
    prefix = f"{run_key}/"
    return (
        key.startswith(prefix) and key.endswith(".parquet") and "/" not in key.removeprefix(prefix)
    )


def read_cells(store: Store, key: str) -> pa.Table:
    """Every cell the run at a key wrote, as one table.

    Raises:
        FileNotFoundError: When the run wrote no cells.
    """
    files = [k for k in store.keys(f"{key}/") if is_cell(k, key)]
    if not files:
        msg = f"no cells under {store.uri(key)}"
        raise FileNotFoundError(msg)
    tables = [pq.read_table(pa.BufferReader(store.read(k))) for k in files]
    return pa.concat_tables(tables, promote_options="default")
