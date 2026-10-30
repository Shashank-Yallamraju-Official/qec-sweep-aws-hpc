import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mpi.exchange import Amplitudes

MPIEXEC = shutil.which("mpiexec")
REPO = Path(__file__).parents[2]

pytestmark = pytest.mark.skipif(MPIEXEC is None, reason="needs mpiexec on the path")


def state_under(ranks: int, qubits: int, scratch: Path) -> Amplitudes:
    out = scratch / f"ranks{ranks}"
    out.mkdir()
    program = [sys.executable, "-m", "tests.mpi.under_mpi", str(qubits), str(out)]
    subprocess.run(
        [str(MPIEXEC), "--oversubscribe", "-n", str(ranks), *program],
        check=True,
        cwd=REPO,
        timeout=120,
    )
    return np.concatenate([np.load(out / f"rank{rank}.npy") for rank in range(ranks)])


@pytest.mark.parametrize("ranks", [2, 4])
def test_sharded_run_matches_a_single_rank_run(ranks: int, tmp_path: Path) -> None:
    assert np.allclose(state_under(ranks, 6, tmp_path), state_under(1, 6, tmp_path))


def test_the_command_records_a_run_on_four_ranks(tmp_path: Path) -> None:
    out = tmp_path / "run.json"
    command = [sys.executable, "-m", "mpi.cli", "--qubits", "6", "--layers", "3", "--out", str(out)]
    subprocess.run(
        [str(MPIEXEC), "--oversubscribe", "-n", "4", *command], check=True, cwd=REPO, timeout=120
    )
    record = json.loads(out.read_text())
    assert record["ranks"] == 4
    assert record["gates"]["far"] > 0
    assert record["seconds"]["exchange"] > 0
    assert np.isclose(record["norm"], 1)


def test_the_single_rank_run_is_a_normalised_entangled_state(tmp_path: Path) -> None:
    state = state_under(1, 6, tmp_path)
    assert len(state) == 64
    assert np.isclose(np.linalg.norm(state), 1)
    assert np.count_nonzero(np.abs(state) > 1e-12) > 1
