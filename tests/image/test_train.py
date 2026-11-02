import json
import os
import subprocess
from pathlib import Path

import pytest

IMAGE = os.environ.get("TRAIN_IMAGE", "")


def in_image(tmp_path: Path, *command: str) -> None:
    subprocess.run(
        ["apptainer", "exec", "--bind", str(tmp_path), IMAGE, *command],
        check=True,
        timeout=600,
    )


@pytest.mark.skipif(not IMAGE, reason="set TRAIN_IMAGE to a built train.sif")
def test_image_samples_a_cell_and_trains_on_it(tmp_path: Path) -> None:
    samples, model = tmp_path / "samples", tmp_path / "model"
    sample = ("--d", "3", "--p", "0.01", "--shots", "400", "--seed", "1", "--out", str(samples))
    in_image(tmp_path, "decoder-sample", *sample)
    train = ("--samples", str(samples), "--out", str(model), "--epochs", "1", "--batch", "64")
    in_image(tmp_path, "decoder-train", *train)
    record = json.loads((model / "train.json").read_text())
    assert (model / "decoder.pt").exists()
    assert record["cell"]["distance"] == 3
    assert record["epochs"] == 1
    assert record["device"] == "cpu"
