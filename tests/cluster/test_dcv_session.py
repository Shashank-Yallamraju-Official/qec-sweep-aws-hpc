import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "cluster" / "dcv-session.sh"
NODE = "i-0123456789abcdef0"

# A stand-in aws: finds the node, accepts a command, reports it done, and answers the
# connect script's line; the port forward is logged and returns at once.
AWS = f"""#!/usr/bin/env bash
echo "aws $*" >> "$STUB_LOG"
case "$1 $2" in
  "ec2 describe-instances") echo "{NODE}" ;;
  "ssm send-command") file=${{@: -1}}; cat "${{file#file://}}" >> "$STUB_LOG"; echo "cmd-1" ;;
  "ssm get-command-invocation")
    if [[ $* == *StandardOutputContent* ]]; then
      echo "PclusterDcvServerPort=8443 PclusterDcvSessionId=abc123 PclusterDcvSessionToken=tok-456"
    else echo Success; fi ;;
  "ssm start-session") echo "forwarding" ;;
esac
"""


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "aws").write_text(AWS)
    (bin_dir / "open").write_text('#!/usr/bin/env bash\necho "open $*" >> "$STUB_LOG"\n')
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    return bin_dir


def session(bin_dir: Path, *options: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_LOG": str(bin_dir.parent / "calls"),
        "AWS_PROFILE": "qec",
    }
    return subprocess.run(
        ["bash", SCRIPT, *options], env=env, capture_output=True, text=True, check=False
    )


def calls(bin_dir: Path) -> str:
    return (bin_dir.parent / "calls").read_text()


def test_the_desktop_opens_on_localhost_through_a_port_forward(bin_dir: Path) -> None:
    result = session(bin_dir)
    assert result.returncode == 0, result.stderr
    log = calls(bin_dir)
    assert "parallelcluster:node-type,Values=LoginNode" in log
    assert f"--target {NODE} --document-name AWS-StartPortForwardingSession" in log
    assert "portNumber=8443,localPortNumber=8443" in log
    assert "pcluster_dcv_connect.sh /home/ubuntu" in log
    assert "open https://localhost:8443?authToken=tok-456#abc123" in log
    assert "https://localhost:8443?authToken=tok-456#abc123" in result.stdout


def test_a_certificate_is_installed_on_the_node_before_the_session(
    bin_dir: Path, tmp_path: Path
) -> None:
    cert, key = tmp_path / "localhost.pem", tmp_path / "localhost.key"
    cert.write_text("CERT\n")
    key.write_text("KEY\n")
    result = session(bin_dir, "-c", str(cert), "-k", str(key))
    assert result.returncode == 0, result.stderr
    log = calls(bin_dir)
    assert "/etc/dcv/dcv.pem" in log
    assert "/etc/dcv/dcv.key" in log
    assert "CERT" in log
    assert "KEY" in log
    assert "systemctl restart dcvserver" in log
    assert log.index("dcv.pem") < log.index("pcluster_dcv_connect.sh")


def test_the_cluster_may_be_named(bin_dir: Path) -> None:
    result = session(bin_dir, "qec-arm")
    assert result.returncode == 0, result.stderr
    assert "parallelcluster:cluster-name,Values=qec-arm" in calls(bin_dir)
