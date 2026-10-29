import subprocess
from pathlib import Path

from sweep.parquet import read


def test_sweep_command_writes_a_readable_result(tmp_path: Path) -> None:
    run = subprocess.run(
        ["sweep", "--d", "3", "--p", "0.01", "--shots", "1000", "--out", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    path = Path(run.stdout.strip())
    assert path.parent == tmp_path
    result = read(path)
    low, high = result.interval
    assert result.cell.shots == 1000
    assert low <= result.logical_error_rate <= high
