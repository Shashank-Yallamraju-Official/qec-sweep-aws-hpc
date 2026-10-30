import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

IMAGE = os.environ.get("MPI_IMAGE", "")


@pytest.mark.skipif(not IMAGE, reason="set MPI_IMAGE to a built mpi.sif")
def test_image_runs_the_circuit_on_four_ranks_with_its_own_mpi(tmp_path: Path) -> None:
    out = tmp_path / "run.json"
    subprocess.run(
        [
            "apptainer",
            "exec",
            "--bind",
            str(tmp_path),
            IMAGE,
            "mpirun",
            "--oversubscribe",
            "-n",
            "4",
            "statevector",
            "--qubits",
            "8",
            "--layers",
            "2",
            "--out",
            str(out),
        ],
        check=True,
        timeout=300,
    )
    record = json.loads(out.read_text())
    assert record["ranks"] == 4
    assert record["gates"]["far"] > 0
    assert np.isclose(record["norm"], 1)
