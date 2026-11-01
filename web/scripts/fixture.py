"""Write a small store of made-up runs, laid out like the bucket, for development and tests.

usage: uv run web/scripts/fixture.py <store dir>

Three sweep runs over a 5 x 8 grid: a reference, a second seed of the same decoder,
and a run whose decoder is better at every distance; plus one state-vector run so the
catalogue has a kind without cells. Error counts follow a threshold curve, so the
plots look like the real thing without a second of decoding.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.parquet import write

DISTANCES = (3, 5, 7, 9, 11)
NOISE_RATES = tuple(float(f"{p:.5g}") for p in (1e-3 * 1.5**i for i in range(8)))
SHOTS = 100_000
THRESHOLD = 0.0095


def logical_error_rate(distance: int, noise: float, factor: float) -> float:
    """A textbook threshold curve, scaled by how good the decoder is."""
    return min(0.5, float(factor * 0.08 * (noise / THRESHOLD) ** ((distance + 1) / 2)))


def record(run: str, seed: int, digest: str, parents: list[str]) -> dict[str, object]:
    """A full run record, as ``jobs/sweep.sh`` and ``jobs/sync.sbatch`` write one."""
    submitted = datetime.strptime(run, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    return {
        "run": run,
        "queue": "sweep",
        "nodes": 16,
        "nodes_used": 16,
        "instance_type": "c7a.large",
        "image": "oras://ghcr.io/example/qec-sweep-aws-hpc/sweep:0d0eebc",
        "image_digest": digest,
        "commit": "0d0eebc668dbcbf66e3eea1245a8d9937afc5af8",
        "cluster_config_sha256": "0340aaf1" * 8,
        "jobs": {"array": 202, "sync": 203},
        "seed": seed,
        "parents": parents,
        "submitted": submitted.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished": (submitted + timedelta(minutes=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_sweep(root: Path, run: str, seed: int, factor: float, parents: list[str]) -> None:
    """One sweep run: its record and a cell file per grid point."""
    digest = f"sha256:{hash((run, factor)) & 0xFFFFFFFFFFFFFFFF:016x}{'0' * 48}"
    directory = root / "sweeps" / run
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(record(run, seed, digest, parents)))
    rng = random.Random(seed)  # noqa: S311
    started = datetime.strptime(run, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    for i, (distance, noise) in enumerate((d, p) for p in NOISE_RATES for d in DISTANCES):
        rate = logical_error_rate(distance, noise, factor)
        errors = max(0, round(rng.gauss(rate * SHOTS, math.sqrt(rate * SHOTS))))
        result = CellResult(
            cell=Cell(distance, noise, SHOTS),
            errors=errors,
            seconds=2.0 + distance * 0.6,
            seed=seed,
            started=started + timedelta(seconds=10 * i),
            host=f"sweep-dy-c7a-{1 + i % 16}",
        )
        write(result, directory)


def write_statevector(root: Path, run: str) -> None:
    """One state-vector run: a record and its per-node timings, no cells."""
    directory = root / "statevector" / run
    directory.mkdir(parents=True)
    submitted = datetime.strptime(run, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    (directory / "run.json").write_text(
        json.dumps(
            {
                "run": run,
                "queue": "mpi",
                "image": "oras://ghcr.io/example/qec-sweep-aws-hpc/mpi:6e27c9b",
                "image_digest": f"sha256:{'9d217f8c' * 8}",
                "commit": "207f3e58dd9fcd668a235d32b07ef4ecea6832da",
                "cluster_config_sha256": "0340aaf1" * 8,
                "ranks_per_node": 2,
                "qubits": 25,
                "layers": 6,
                "jobs": {"1": 50, "2": 51},
                "parents": [],
                "submitted": submitted.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "finished": (submitted + timedelta(minutes=9)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    )
    (directory / "nodes1.json").write_text("{}")


def main(argv: Sequence[str] | None = None) -> int:
    """Write the fixture store.

    Returns:
        Exit status: 0 on success, 2 when the directory already exists.
    """
    parser = argparse.ArgumentParser(prog="fixture", description="write a store of made-up runs")
    parser.add_argument("store", type=Path, help="directory to create")
    args = parser.parse_args(argv)
    if args.store.exists():
        print(f"fixture: {args.store} exists; remove it first", file=sys.stderr)
        return 2
    # A parent is named by its full address, which for a directory is its absolute path.
    reference = str(args.store.resolve() / "sweeps" / "20261030T204955Z")
    write_sweep(args.store, "20261030T204955Z", seed=0, factor=1.0, parents=[])
    write_sweep(args.store, "20261101T171838Z", seed=1, factor=1.0, parents=[reference])
    write_sweep(args.store, "20261102T090000Z", seed=0, factor=0.8, parents=[reference])
    write_statevector(args.store, "20261030T231737Z")
    print(f"4 runs -> {args.store}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
