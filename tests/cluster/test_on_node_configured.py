import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "cluster" / "on-node-configured.sh"

STUBS = {
    # apt-get and the rest are logged, never run; apptainer is present so no install runs.
    "apt-get": '#!/usr/bin/env bash\necho "apt-get $*" >> "$STUB_LOG"\n',
    "apptainer": '#!/usr/bin/env bash\necho "apptainer version 1.5.5"\n',
    "dpkg": "#!/usr/bin/env bash\necho amd64\n",
}


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, script in STUBS.items():
        (bin_dir / name).write_text(script)
        (bin_dir / name).chmod(0o755)
    return bin_dir


def configure(bin_dir: Path, node_type: str) -> list[str]:
    config = bin_dir.parent / "cfnconfig"
    config.write_text(f'cfn_node_type="{node_type}"\n')
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_LOG": str(bin_dir.parent / "calls"),
        "CFNCONFIG": str(config),
    }
    result = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    log = bin_dir.parent / "calls"
    return log.read_text().splitlines() if log.exists() else []


def test_a_login_node_gets_paraview(bin_dir: Path) -> None:
    calls = configure(bin_dir, "LoginNode")
    assert any(c.startswith("apt-get install") and "paraview" in c for c in calls)


def test_a_compute_node_does_not(bin_dir: Path) -> None:
    assert not any("paraview" in c for c in configure(bin_dir, "ComputeFleet"))


def test_a_node_without_the_cluster_file_is_a_compute_node(bin_dir: Path) -> None:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_LOG": str(bin_dir.parent / "calls"),
        "CFNCONFIG": str(bin_dir.parent / "missing"),
    }
    result = subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert not (bin_dir.parent / "calls").exists()
