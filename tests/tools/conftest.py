import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.parquet import write

REPOSITORY = "example/qec"
SHA = "0d0eebc668dbcbf66e3eea1245a8d9937afc5af8"
IMAGE = f"oras://ghcr.io/example/qec/sweep:{SHA}"
COMMITTED = datetime(2026, 10, 31, 0, 11, 35, tzinfo=UTC)
BUILT = datetime(2026, 10, 31, 0, 12, 52, tzinfo=UTC)
SUBMITTED = datetime(2026, 10, 31, 0, 20, 0, tzinfo=UTC)
FIRST = datetime(2026, 10, 31, 0, 25, 0, tzinfo=UTC)

GITHUB: dict[str, Any] = {
    f"repos/{REPOSITORY}/commits/{SHA}": {
        "commit": {"committer": {"date": "2026-10-31T00:11:35Z"}}
    },
    f"repos/{REPOSITORY}/actions/runs?head_sha={SHA}&per_page=100": {
        "workflow_runs": [
            {
                "name": "ci",
                "jobs_url": "https://api.github.com/repos/example/qec/actions/runs/1/jobs",
            },
            {
                "name": "image",
                "jobs_url": "https://api.github.com/repos/example/qec/actions/runs/2/jobs",
            },
        ]
    },
    "https://api.github.com/repos/example/qec/actions/runs/2/jobs": {
        "jobs": [
            {"name": "image (mpi)", "completed_at": "2026-10-31T00:15:42Z"},
            {"name": "image (sweep)", "completed_at": "2026-10-31T00:12:52Z"},
        ]
    },
}


def fetch(path: str) -> Any:  # noqa: ANN401
    """GitHub as the fakes above describe it."""
    return GITHUB[path]


def write_run(
    root: Path,
    run: str = "20261031T002000Z",
    submitted: datetime = SUBMITTED,
    first_cell: datetime = FIRST,
    **fields: object,
) -> str:
    """A run under ``sweeps/<run>`` with three cells, the earliest at ``first_cell``."""
    run_dir = root / "sweeps" / run
    run_dir.mkdir(parents=True)
    record: dict[str, object] = {
        "run": run,
        "queue": "sweep",
        "image": IMAGE,
        "instance_type": "c7a.large",
        "nodes": 4,
        "submitted": submitted.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished": (submitted + timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **fields,
    }
    (run_dir / "run.json").write_text(json.dumps(record))
    starts = (first_cell + timedelta(seconds=30), first_cell, first_cell + timedelta(minutes=1))
    for distance, started in zip((3, 5, 7), starts, strict=True):
        result = CellResult(
            cell=Cell(distance, 0.01, 1000),
            errors=1,
            seconds=1.0,
            seed=0,
            started=started,
            host="n",
        )
        write(result, run_dir)
    return f"sweeps/{run}"
