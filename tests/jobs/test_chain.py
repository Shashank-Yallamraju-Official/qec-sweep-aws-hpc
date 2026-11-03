import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "ab" * 32
SWEEP_IMAGE = "oras://ghcr.io/example/qec/sweep:abc"
TRAIN_IMAGE = "oras://ghcr.io/example/qec/train:abc"

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
        "#!/usr/bin/env bash\nname=${1##*/}; name=${name%%:*}\n"
        f'echo "{DIGEST} /scratch/images/$name.sif"\n'
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


def chain(
    jobs: Path, *cells: str, options: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    command: list[str | Path] = [
        "bash",
        jobs / "chain.sh",
        *options,
        SWEEP_IMAGE,
        TRAIN_IMAGE,
        "s3://bucket",
        "sweep",
    ]
    return subprocess.run(
        [*command, "500", "1000", *cells],
        env=env(jobs),
        capture_output=True,
        text=True,
        check=False,
    )


def submissions(jobs: Path) -> list[str]:
    return [c for c in (jobs.parent / "calls").read_text().splitlines() if c.startswith("sbatch")]


def runs(jobs: Path, kind: str) -> list[Path]:
    return sorted((jobs.parent / "scratch" / "tester" / kind).iterdir())


def record(path: Path) -> dict[str, object]:
    return dict(json.loads((path / "run.json").read_text()))


def test_the_chain_wires_generate_train_evaluate_and_report_by_dependency(jobs: Path) -> None:
    result = chain(jobs, "3:0.005", "5:0.005", options=("-r", "0.001", "-r", "0.002", "-c", "2"))
    assert result.returncode == 0, result.stderr
    calls = submissions(jobs)
    assert len(calls) == 14
    generate_3, _, train_3, _, generate_5, _, train_5, _, matching, _, learned, _, report, sync = (
        calls
    )
    assert "--array=0-1 " in generate_3
    assert "CELLS=3:0.005" in generate_3
    assert "--dependency=afterok:101" in train_3
    assert "--array=0-1 " in generate_5
    assert "CELLS=5:0.005" in generate_5
    assert "--dependency=afterok:105" in train_5
    assert "CELLS=3:0.001 3:0.002 5:0.001 5:0.002" in matching
    assert "DECODER=pymatching" in matching
    assert "--dependency" not in matching
    assert "DECODER=learned" in learned
    assert "--dependency=afterok:103:107" in learned
    (train_dir_3, train_dir_5) = runs(jobs, "train")
    assert f"MODELS=3={train_dir_3}/model/decoder.pt 5={train_dir_5}/model/decoder.pt" in learned
    assert "SWEEP_IMAGE=/scratch/images/train.sif" in learned
    assert "SWEEP_IMAGE=/scratch/images/sweep.sif" in matching
    assert "--dependency=afterok:109:111" in report
    assert "REPORT_IMAGE=/scratch/images/train.sif" in report
    (matching_dir, learned_dir) = runs(jobs, "evaluations")
    assert f"MATCHING={matching_dir}" in report
    assert f"LEARNED={learned_dir}" in report
    assert "--dependency=afterany:113" in sync
    assert "OUTPUTS=report" in sync
    assert "DESTINATION=s3://bucket/chains" in sync


def test_the_chain_record_names_every_child_run(jobs: Path) -> None:
    result = chain(jobs, "3:0.005", options=("-s", "7", "-n", "correlated", "-e", "3", "-N", "2"))
    assert result.returncode == 0, result.stderr
    (chain_dir,) = runs(jobs, "chains")
    got = record(chain_dir)
    (generate_dir,) = runs(jobs, "generate")
    (train_dir,) = runs(jobs, "train")
    matching_dir, learned_dir = runs(jobs, "evaluations")
    assert got["seed"] == 7
    assert got["noise"] == "correlated"
    assert got["cells"] == ["3:0.005"]
    assert got["rates"] == ["0.005"]
    assert got["shots"] == {"generate": 500, "chunks": 1, "evaluate": 1000}
    assert got["epochs"] == 3
    assert got["train_nodes"] == 2
    assert got["image"] == SWEEP_IMAGE
    assert got["train_image"] == TRAIN_IMAGE
    assert got["children"] == {
        "generate": [f"s3://bucket/generate/{generate_dir.name}"],
        "train": [f"s3://bucket/train/{train_dir.name}"],
        "evaluations": {
            "pymatching": f"s3://bucket/evaluations/{matching_dir.name}",
            "learned": f"s3://bucket/evaluations/{learned_dir.name}",
        },
    }
    assert got["jobs"] == {"report": 109, "sync": 110}
    chain_uri = f"s3://bucket/chains/{chain_dir.name}"
    assert record(generate_dir)["parents"] == [chain_uri]
    assert record(train_dir)["parents"] == [chain_uri, f"s3://bucket/generate/{generate_dir.name}"]
    assert record(train_dir)["nodes"] == 2
    assert record(train_dir)["epochs"] == 3
    assert record(learned_dir)["parents"] == [chain_uri, f"s3://bucket/train/{train_dir.name}"]
    assert record(matching_dir)["parents"] == [chain_uri]
    assert record(matching_dir)["noise"] == "correlated"


def test_the_report_job_compares_the_two_evaluations(jobs: Path, tmp_path: Path) -> None:
    run_dir = tmp_path / "chain"
    (run_dir / "report").mkdir(parents=True)
    job_env = env(
        jobs,
        RUN_DIR=str(run_dir),
        REPORT_IMAGE="/scratch/images/train.sif",
        MATCHING="/scratch/tester/evaluations/a",
        LEARNED="/scratch/tester/evaluations/b",
    )
    result = subprocess.run(
        ["bash", jobs / "report.sbatch"], env=job_env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    (call,) = (jobs.parent / "calls").read_text().splitlines()
    assert call.startswith(
        "apptainer exec --bind /scratch /scratch/images/train.sif results-compare "
    )
    assert "/scratch/tester/evaluations/a /scratch/tester/evaluations/b" in call
    assert f"--out {run_dir}/report/comparison.parquet" in call
    assert (run_dir / "report" / "comparison.txt").exists()
