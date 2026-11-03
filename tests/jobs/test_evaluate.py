import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "ab" * 32
IMAGE = "oras://ghcr.io/example/qec/train:abc"

STUBS = {
    # Job ids count up from 100; every call is logged for the test to read.
    "sbatch": '#!/usr/bin/env bash\necho "sbatch $*" >> "$STUB_LOG"\n'
    'n=$(grep -c "^sbatch" "$STUB_LOG"); echo $((100 + n))\n',
    "apptainer": '#!/usr/bin/env bash\necho "apptainer $*" >> "$STUB_LOG"\n',
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


def evaluate(
    jobs: Path, *cells: str, options: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    command: list[str | Path] = ["bash", jobs / "evaluate.sh", *options]
    command += [IMAGE, "s3://bucket/evaluations", "sweep"]
    return subprocess.run(
        [*command, "1000", *cells], env=env(jobs), capture_output=True, text=True, check=False
    )


def calls(jobs: Path) -> list[str]:
    return (jobs.parent / "calls").read_text().splitlines()


def record(jobs: Path) -> dict[str, object]:
    (run_dir,) = (jobs.parent / "scratch" / "tester" / "evaluations").iterdir()
    return dict(json.loads((run_dir / "run.json").read_text()))


def test_one_array_task_per_cell_decoded_by_matching(jobs: Path) -> None:
    result = evaluate(jobs, "3:0.001", "3:0.002", "5:0.001")
    assert result.returncode == 0, result.stderr
    array, sync = calls(jobs)
    assert "--partition sweep" in array
    assert "--array=0-2 " in array
    assert "--dependency" not in array
    assert "CELLS=3:0.001 3:0.002 5:0.001" in array
    assert "SHOTS=1000" in array
    assert "DECODER=pymatching" in array
    assert "MODELS= " in array or "MODELS=," in array
    assert "SWEEP_IMAGE=/scratch/images/ab.sif" in array
    assert "--dependency=afterany:101" in sync
    assert "OUTPUTS" not in sync
    got = record(jobs)
    assert got["decoder"] == "pymatching"
    assert got["models"] == {}
    assert got["cells"] == ["3:0.001", "3:0.002", "5:0.001"]
    assert got["shots"] == 1000
    assert got["noise"] == "depolarising"
    assert got["jobs"] == {"array": 101, "sync": 102}


def test_the_learned_decoder_takes_a_model_per_distance_and_waits_for_training(
    jobs: Path,
) -> None:
    options: tuple[str, ...] = (
        "-D",
        "learned",
        "-m",
        "3=/scratch/t/3/model/decoder.pt",
        "-m",
        "5=/scratch/t/5/model/decoder.pt",
    )
    options += ("-a", "40:41", "-n", "correlated", "-s", "4", "-p", "s3://bucket/chains/c")
    result = evaluate(jobs, "3:0.001", "5:0.001", options=options)
    assert result.returncode == 0, result.stderr
    array = calls(jobs)[0]
    assert "--dependency=afterok:40:41" in array
    assert "DECODER=learned" in array
    assert "MODELS=3=/scratch/t/3/model/decoder.pt 5=/scratch/t/5/model/decoder.pt" in array
    assert "NOISE=correlated" in array
    assert "SEED=4" in array
    got = record(jobs)
    assert got["decoder"] == "learned"
    assert got["models"] == {
        "3": "/scratch/t/3/model/decoder.pt",
        "5": "/scratch/t/5/model/decoder.pt",
    }
    assert got["parents"] == ["s3://bucket/chains/c"]
    assert got["image"] == IMAGE
    assert got["image_digest"] == DIGEST
    assert got["seed"] == 4


def test_the_learned_decoder_needs_a_model_for_every_distance(jobs: Path) -> None:
    result = evaluate(jobs, "3:0.001", "5:0.001", options=("-D", "learned", "-m", "3=/m3.pt"))
    assert result.returncode == 2
    assert "distance 5" in result.stderr
    assert not (jobs.parent / "calls").exists()


def test_a_decoder_must_be_known(jobs: Path) -> None:
    result = evaluate(jobs, "3:0.001", options=("-D", "oracle"))
    assert result.returncode == 2
    assert "oracle" in result.stderr


def test_an_array_task_decodes_its_cell_with_its_distances_model(
    jobs: Path, tmp_path: Path
) -> None:
    task_env = env(
        jobs,
        SLURM_ARRAY_TASK_ID="1",
        SLURMD_NODENAME="node-2",
        RUN_DIR=str(tmp_path / "run"),
        SWEEP_IMAGE="/scratch/images/ab.sif",
        CELLS="3:0.001 5:0.002",
        SHOTS="1000",
        SEED="4",
        NOISE="correlated",
        DECODER="learned",
        MODELS="3=/m/3.pt 5=/m/5.pt",
    )
    (tmp_path / "run").mkdir()
    result = subprocess.run(
        ["bash", jobs / "evaluate.sbatch"],
        env=task_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    (call,) = calls(jobs)
    assert call.startswith("apptainer run --bind /scratch /scratch/images/ab.sif ")
    assert "--d 5 --p 0.002 --shots 1000 --seed 4 --noise correlated" in call
    assert "--decoder learned --model /m/5.pt" in call
    assert call.endswith(f"--out {tmp_path / 'run' / 'cells'}")
    assert (tmp_path / "run" / "nodes" / "node-2").exists()


def test_a_matching_task_names_no_model(jobs: Path, tmp_path: Path) -> None:
    task_env = env(
        jobs,
        SLURM_ARRAY_TASK_ID="0",
        SLURMD_NODENAME="node-1",
        RUN_DIR=str(tmp_path / "run"),
        SWEEP_IMAGE="/scratch/images/ab.sif",
        CELLS="3:0.001",
        SHOTS="1000",
        SEED="0",
        NOISE="depolarising",
        DECODER="pymatching",
        MODELS="",
    )
    (tmp_path / "run").mkdir()
    result = subprocess.run(
        ["bash", jobs / "evaluate.sbatch"],
        env=task_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    (call,) = calls(jobs)
    assert "--decoder" not in call
    assert "--model" not in call
