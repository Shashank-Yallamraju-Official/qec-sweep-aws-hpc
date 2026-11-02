import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "ab" * 32
IMAGE = "oras://ghcr.io/example/qec/train:abc"
PARENT = "s3://bucket/training/20261101T000000Z"

STUBS = {
    # Job ids count up from 100; every call is logged for the test to read.
    "sbatch": '#!/usr/bin/env bash\necho "sbatch $*" >> "$STUB_LOG"\n'
    'n=$(wc -l < "$STUB_LOG"); echo $((100 + n))\n',
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
    (tmp_path / "samples").mkdir()
    return copy


def train(
    jobs: Path, *options: str, queue: tuple[str, ...] = (), config: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{jobs.parent / 'bin'}:{os.environ['PATH']}",
        "STUB_LOG": str(jobs.parent / "calls"),
        "SCRATCH": str(jobs.parent / "scratch"),
        "USER": "tester",
        "CLUSTER_CONFIG": str(config or jobs.parent / "no-config.yaml"),
    }
    samples = jobs.parent / "samples"
    return subprocess.run(
        ["bash", jobs / "train.sh", *options, IMAGE, "s3://bucket/train", str(samples), *queue],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def record(jobs: Path) -> dict[str, object]:
    (run_dir,) = (jobs.parent / "scratch" / "tester" / "train").iterdir()
    return dict(json.loads((run_dir / "run.json").read_text()))


def submissions(jobs: Path) -> list[str]:
    return (jobs.parent / "calls").read_text().splitlines()


def test_a_training_run_submits_one_job_and_its_sync(jobs: Path) -> None:
    result = train(jobs, "-p", PARENT, "-e", "20", "-l", "0.002")
    assert result.returncode == 0, result.stderr
    job, sync = submissions(jobs)
    assert "--partition train" in job
    assert f"SAMPLES={jobs.parent / 'samples'}" in job
    assert "EPOCHS=20" in job
    assert "LEARNING_RATE=0.002" in job
    assert "DEVICE=cpu" in job
    assert "TRAIN_IMAGE=/scratch/images/ab.sif" in job
    assert "--dependency=afterany:101" in sync
    assert "OUTPUTS=model" in sync
    assert record(jobs) == {
        **record(jobs),
        "queue": "train",
        "image": IMAGE,
        "image_digest": DIGEST,
        "parents": [PARENT],
        "seed": 0,
        "epochs": 20,
        "learning_rate": 0.002,
        "device": "cpu",
        "jobs": {"train": 101, "sync": 102},
        "scaledown_idle_minutes": None,
    }
    assert str(record(jobs)["samples"]) == str(jobs.parent / "samples")


def test_a_run_may_name_its_queue_and_device(jobs: Path) -> None:
    result = train(jobs, "-s", "7", "-d", "cuda", queue=("gpu",))
    assert result.returncode == 0, result.stderr
    assert "--partition gpu" in submissions(jobs)[0]
    assert "DEVICE=cuda" in submissions(jobs)[0]
    assert record(jobs)["seed"] == 7
    assert record(jobs)["device"] == "cuda"


def test_a_run_records_the_idle_tail_from_the_cluster_configuration(
    jobs: Path, tmp_path: Path
) -> None:
    config = tmp_path / "cluster-config.yaml"
    config.write_text("Scheduling:\n  SlurmSettings:\n    ScaledownIdletime: 3\n")
    result = train(jobs, config=config)
    assert result.returncode == 0, result.stderr
    assert record(jobs)["scaledown_idle_minutes"] == 3
    assert record(jobs)["cluster_config_sha256"]


def test_a_missing_samples_directory_is_refused(jobs: Path) -> None:
    shutil.rmtree(jobs.parent / "samples")
    result = train(jobs)
    assert result.returncode == 2
    assert "samples" in result.stderr
