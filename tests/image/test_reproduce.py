import json
import os
import platform
import subprocess
from pathlib import Path

import pytest

from sweep.decode import CellResult, wilson_interval
from sweep.parquet import read

IMAGE = os.environ.get("SWEEP_IMAGE", "")
REFERENCE = json.loads((Path(__file__).resolve().parents[2] / "image/hand-built.json").read_text())
HAND_BUILT_ARCHITECTURE = "x86_64"
Z_9999 = 3.89


@pytest.mark.skipif(not IMAGE, reason="set SWEEP_IMAGE to a built sweep.sif")
@pytest.mark.skipif(
    platform.machine() != HAND_BUILT_ARCHITECTURE,
    reason="Stim's samples are bit-identical only within an architecture",
)
def test_image_reproduces_the_hand_built_cell(tmp_path: Path) -> None:
    assert decode_reference_cell(tmp_path).errors == REFERENCE["errors"]


@pytest.mark.skipif(not IMAGE, reason="set SWEEP_IMAGE to a built sweep.sif")
@pytest.mark.skipif(
    platform.machine() == HAND_BUILT_ARCHITECTURE,
    reason="on the hand-built architecture the count is reproduced exactly",
)
def test_image_agrees_with_the_hand_built_cell_on_another_architecture(tmp_path: Path) -> None:
    low, high = wilson_interval(REFERENCE["errors"], REFERENCE["shots"], z=Z_9999)
    assert low <= decode_reference_cell(tmp_path).errors / REFERENCE["shots"] <= high


def decode_reference_cell(tmp_path: Path) -> CellResult:
    run = subprocess.run(
        [
            "apptainer",
            "run",
            "--bind",
            str(tmp_path),
            IMAGE,
            "--d",
            str(REFERENCE["distance"]),
            "--p",
            str(REFERENCE["noise"]),
            "--shots",
            str(REFERENCE["shots"]),
            "--seed",
            str(REFERENCE["seed"]),
            "--out",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    (path,) = tmp_path.glob("*.parquet")
    return read(path)
