import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from results.store import LocalStore
from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.parquet import write

FULL_RECORD = {
    "run": "20261030T231737Z",
    "queue": "sweep",
    "nodes": 16,
    "nodes_used": 16,
    "instance_type": "c7a.large",
    "image": "oras://ghcr.io/example/sweep:abc",
    "image_digest": "sha256:9d217f8c",
    "commit": "207f3e5",
    "cluster_config_sha256": "0340aaf1",
    "jobs": {"array": 41, "sync": 42},
    "seed": 7,
    "parents": ["s3://bucket/sweeps/20261030T001136Z"],
    "submitted": "2026-10-30T23:17:37Z",
    "finished": "2026-10-30T23:27:37Z",
}

THIN_RECORD = {
    "run": "20261030T001136Z",
    "queue": "sweep",
    "nodes": 4,
    "instance_type": "c7a.large",
    "image": "oras://ghcr.io/example/sweep:old",
    "submitted": "2026-10-30T00:11:36Z",
    "finished": "2026-10-30T00:21:36Z",
}

STATEVECTOR_RECORD = {
    "run": "20261030T120000Z",
    "queue": "mpi",
    "image": "oras://ghcr.io/example/mpi:abc",
    "image_digest": "sha256:1111",
    "commit": "207f3e5",
    "cluster_config_sha256": "0340aaf1",
    "ranks_per_node": 2,
    "qubits": 25,
    "layers": 6,
    "jobs": {"1": 50, "2": 51},
    "parents": [],
    "submitted": "2026-10-30T12:00:00Z",
    "finished": "2026-10-30T12:05:00Z",
}


def write_run(
    root: Path,
    key: str,
    record: dict[str, object],
    errors: dict[int, int],
    noise_model: str = "depolarising",
) -> None:
    run = root / key
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps(record))
    seed = int(str(record.get("seed", 0)))
    for distance, count in errors.items():
        result = CellResult(
            cell=Cell(distance, 0.01, 1000),
            errors=count,
            seconds=1.0,
            seed=seed,
            started=datetime(2026, 10, 30, tzinfo=UTC),
            host="node",
            noise_model=noise_model,
        )
        write(result, run)
    (run / "logs").mkdir()
    (run / "logs" / "0.out").write_text("ok\n")


@pytest.fixture
def store(tmp_path: Path) -> LocalStore:
    write_run(tmp_path, "sweeps/20261030T001136Z", THIN_RECORD, {3: 30, 5: 10})
    write_run(tmp_path, "sweeps/20261030T231737Z", FULL_RECORD, {3: 28, 5: 12, 7: 3})
    sv = tmp_path / "statevector/20261030T120000Z"
    sv.mkdir(parents=True)
    (sv / "run.json").write_text(json.dumps(STATEVECTOR_RECORD))
    (sv / "nodes1.json").write_text("{}")
    return LocalStore(tmp_path)
