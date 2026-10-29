import json
import os
import subprocess
from pathlib import Path

import pytest

from sweep.parquet import read

IMAGE = os.environ.get("SWEEP_IMAGE", "")
REFERENCE = json.loads((Path(__file__).resolve().parents[2] / "image/hand-built.json").read_text())


@pytest.mark.skipif(not IMAGE, reason="set SWEEP_IMAGE to a built sweep.sif")
def test_image_reproduces_the_hand_built_cell(tmp_path: Path) -> None:
    subprocess.run(
        [
            "apptainer",
            "run",
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
        check=True,
        capture_output=True,
        text=True,
    )
    (path,) = tmp_path.glob("*.parquet")
    assert read(path).errors == REFERENCE["errors"]
