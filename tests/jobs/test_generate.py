import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "ab" * 32
IMAGE = "oras://ghcr.io/example/qec/sweep:abc"

STUBS = {
    # Job ids count up from 100; every call is logged for the test to read.
    "sbatch": '#!/usr/bin/env bash\necho "sbatch $*" >> "$STUB_LOG"\n'
    'n=$(grep -c "^sbatch" "$STUB_LOG"); echo $((100 + n))\n',
    # A pull writes the file it was asked for and reports the digest, as the real one does.
    "apptainer": '#!/usr/bin/env bash\necho "apptainer $*" >> "$STUB_LOG"\n'
    '[[ $1 == pull ]] && { echo pulled > "${@: -2:1}"; echo "INFO:    Digest: '
    + DIGEST
    + '" >&2; }\nexit 0\n',
}


@pytest.fixture
def jobs(tmp_path: Path) -> Path:
    copy = tmp_path / "jobs"
    shutil.copytree(ROOT / "jobs", copy)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in STUBS.items():
        (bin_dir / name).write_text(script)
        (bin_dir / name).chmod(0o755)
    return copy


def env(jobs: Path, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{jobs.parent / 'bin'}:{os.environ['PATH']}",
        "STUB_LOG": str(jobs.parent / "calls"),
        "SCRATCH": str(jobs.parent / "scratch"),
        "USER": "tester",
        "CLUSTER_CONFIG": str(jobs.parent / "no-config.yaml"),
        **extra,
    }


def generate(
    jobs: Path, *positional: str, options: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    command: list[str | Path] = ["bash", jobs / "generate.sh", *options]
    command += [IMAGE, "s3://bucket/training", "sweep"]
    return subprocess.run(
        [*command, *positional],
        env=env(jobs),
        capture_output=True,
        text=True,
        check=False,
    )


def calls(jobs: Path) -> list[str]:
    return (jobs.parent / "calls").read_text().splitlines()


def record(jobs: Path) -> dict[str, object]:
    (run_dir,) = (jobs.parent / "scratch" / "tester" / "generate").iterdir()
    return dict(json.loads((run_dir / "run.json").read_text()))


def test_one_array_task_per_cell_and_seed_chunk(jobs: Path) -> None:
    result = generate(jobs, "1000", "3:0.001", "3:0.002", "5:0.001", options=("-c", "2"))
    assert result.returncode == 0, result.stderr
    pull, array, sync = calls(jobs)
    assert pull.endswith(f" {IMAGE}")
    assert "--partition sweep" in array
    assert "--array=0-5 " in array
    assert "CELLS=3:0.001 3:0.002 5:0.001" in array
    assert "SHOTS=1000" in array
    assert "CHUNKS=2" in array
    assert "NOISE=depolarising" in array
    assert "--dependency=afterany:101" in sync
    assert "OUTPUTS=samples" in sync
    assert "PATTERN=*.npz" in sync


def test_the_record_names_what_an_audit_needs(jobs: Path) -> None:
    options = ("-s", "10", "-n", "correlated", "-p", "s3://bucket/sweeps/x")
    result = generate(jobs, "500", "3:0.001", options=options)
    assert result.returncode == 0, result.stderr
    got = record(jobs)
    assert got["queue"] == "sweep"
    assert got["image"] == IMAGE
    assert got["image_digest"] == DIGEST
    assert got["jobs"] == {"array": 101, "sync": 102}
    assert got["seed"] == 10
    assert got["parents"] == ["s3://bucket/sweeps/x"]
    assert got["noise"] == "correlated"
    assert got["cells"] == ["3:0.001"]
    assert (got["shots"], got["chunks"]) == (500, 1)
    assert str(got["submitted"]).endswith("Z")
    assert got["commit"] is None
    assert got["cluster_config_sha256"] is None


def test_a_cell_must_be_distance_and_noise(jobs: Path) -> None:
    result = generate(jobs, "1000", "3")
    assert result.returncode == 2
    assert "distance:noise" in result.stderr


def test_an_array_task_samples_its_cell_and_chunk(jobs: Path, tmp_path: Path) -> None:
    task_env = env(
        jobs,
        SLURM_ARRAY_TASK_ID="3",
        SLURMD_NODENAME="node-1",
        RUN_DIR=str(tmp_path / "run"),
        SAMPLE_IMAGE="/scratch/images/ab.sif",
        CELLS="3:0.001 5:0.002",
        SHOTS="1000",
        CHUNKS="2",
        SEED="10",
        NOISE="correlated",
    )
    (tmp_path / "run").mkdir()
    result = subprocess.run(
        ["bash", jobs / "generate.sbatch"],
        env=task_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    (call,) = calls(jobs)
    assert call.startswith("apptainer exec --bind /scratch /scratch/images/ab.sif decoder-sample ")
    assert "--d 5 --p 0.002 --shots 1000 --seed 11 --noise correlated" in call
    assert call.endswith(f"--out {tmp_path / 'run' / 'samples'}")
    assert (tmp_path / "run" / "nodes" / "node-1").exists()
