import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "ab" * 32
IMAGE = "oras://ghcr.io/example/qec/sweep:abc"
QUEUE_SIZE = 16

STUBS = {
    # Job ids count up from 100; every call is logged for the test to read.
    "sbatch": '#!/usr/bin/env bash\necho "sbatch $*" >> "$STUB_LOG"\n'
    'n=$(wc -l < "$STUB_LOG"); echo $((100 + n))\n',
    # Two kinds of node in the x86 queue, one kind in the Graviton queue.
    "sinfo": "#!/usr/bin/env bash\n"
    "queue=${2:?}; kinds=(c7a c7i); [[ $queue == *arm ]] && kinds=(c8g)\n"
    'for kind in "${kinds[@]}"; do for i in $(seq 1 16); do echo "$queue-dy-$kind-$i"; done; done\n'
    "",
    # The grid inside the image has 200 cells.
    "apptainer": "#!/usr/bin/env bash\necho 199\n",
}


@pytest.fixture
def jobs(tmp_path: Path) -> Path:
    """A copy of the job scripts whose image pull is a stand-in, since there is no registry."""
    copy = tmp_path / "jobs"
    shutil.copytree(ROOT / "jobs", copy)
    (copy / "pull-image.sh").write_text(
        f'#!/usr/bin/env bash\necho "{DIGEST} /scratch/images/ab.sif"\n'
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in STUBS.items():
        (bin_dir / name).write_text(script)
        (bin_dir / name).chmod(0o755)
    return copy


def sweep(
    jobs: Path, *options: str, where: tuple[str, ...] = (), config: Path | None = None
) -> subprocess.CompletedProcess[str]:
    scratch = jobs.parent / "scratch"
    env = {
        **os.environ,
        "PATH": f"{jobs.parent / 'bin'}:{os.environ['PATH']}",
        "STUB_LOG": str(jobs.parent / "calls"),
        "SCRATCH": str(scratch),
        "USER": "tester",
        "CLUSTER_CONFIG": str(config or jobs.parent / "no-config.yaml"),
    }
    return subprocess.run(
        [jobs / "sweep.sh", *options, IMAGE, "s3://bucket/sweeps", *where],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def record(jobs: Path) -> dict[str, object]:
    (run_dir,) = (jobs.parent / "scratch" / "tester" / "sweep").iterdir()
    return dict(json.loads((run_dir / "run.json").read_text()))


def submissions(jobs: Path) -> list[str]:
    return (jobs.parent / "calls").read_text().splitlines()


def test_a_run_pins_its_type_and_records_it(jobs: Path) -> None:
    result = sweep(jobs)
    assert result.returncode == 0, result.stderr
    array, sync = submissions(jobs)
    assert "--partition sweep" in array
    assert "--constraint c7a.large" in array
    assert "--array=0-199 " in array
    assert "--exclude" not in array
    assert "--dependency=afterany:101" in sync
    assert record(jobs) == {
        **record(jobs),
        "instance_type": "c7a.large",
        "nodes": None,
        "image_digest": DIGEST,
        "jobs": {"array": 101, "sync": 102},
        "scaledown_idle_minutes": None,
    }


def test_a_node_count_fills_that_many_nodes_of_the_chosen_type(jobs: Path) -> None:
    result = sweep(jobs, "-t", "c8g.large", where=("sweep-arm", "4"))
    assert result.returncode == 0, result.stderr
    array = submissions(jobs)[0]
    assert "--partition sweep-arm" in array
    assert "--constraint c8g.large" in array
    assert "--array=0-199%8" in array
    assert "--exclude sweep-arm-dy-c8g-[5-16]" in array
    assert record(jobs)["instance_type"] == "c8g.large"
    assert record(jobs)["nodes"] == 4
    assert record(jobs)["queue"] == "sweep-arm"


def test_a_run_on_every_node_of_a_type_excludes_none(jobs: Path) -> None:
    result = sweep(jobs, "-t", "c7i.large", where=("sweep", str(QUEUE_SIZE)))
    assert result.returncode == 0, result.stderr
    assert "--exclude" not in submissions(jobs)[0]


def test_a_run_records_the_idle_tail_from_the_cluster_configuration(
    jobs: Path, tmp_path: Path
) -> None:
    config = tmp_path / "cluster-config.yaml"
    config.write_text("Scheduling:\n  SlurmSettings:\n    ScaledownIdletime: 3\n")
    result = sweep(jobs, config=config)
    assert result.returncode == 0, result.stderr
    assert record(jobs)["scaledown_idle_minutes"] == 3
    assert record(jobs)["cluster_config_sha256"]


def test_a_type_must_name_a_family_and_a_size(jobs: Path) -> None:
    result = sweep(jobs, "-t", "large")
    assert result.returncode == 2
    assert "instance type" in result.stderr
