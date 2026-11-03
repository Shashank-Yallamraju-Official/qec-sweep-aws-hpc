import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "cluster" / "dcv-session.sh"
NODE = "i-0123456789abcdef0"
CONNECT_LINE = (  # what ParallelCluster's connect script prints, with a made-up token
    "PclusterDcvServerPort=8443 PclusterDcvSessionId=abc123 PclusterDcvSessionToken=tok-456"
)

# A stand-in aws: finds the node, accepts a command and keeps its script, reports it done,
# and answers by what the script asked: the names the node serves (localhost once a
# certificate has been installed), a signing request, or the connect script's line.
# The port forward is logged and returns at once.
AWS = f"""#!/usr/bin/env bash
echo "aws $*" >> "$STUB_LOG"
case "$1 $2" in
  "ec2 describe-instances") echo "{NODE}" ;;
  "ssm send-command")
    file=${{@: -1}}
    cp "${{file#file://}}" "$STUB_DIR/last.json"
    cat "$STUB_DIR/last.json" >> "$STUB_LOG"
    echo "cmd-1" ;;
  "ssm get-command-invocation")
    if [[ $* != *StandardOutputContent* ]]; then echo Success; exit 0; fi
    last=$(cat "$STUB_DIR/last.json")
    if [[ $last == *s_client* ]]; then
      if [[ -f $STUB_DIR/trusted ]]; then echo "DNS:localhost, IP Address:127.0.0.1"
      else echo "DNS:ip-172-31-30-30"; fi
    elif [[ $last == *"openssl req"* ]]; then
      printf -- "-----BEGIN CERTIFICATE REQUEST-----\\nREQUEST\\n"
      printf -- "-----END CERTIFICATE REQUEST-----\\n"
    elif [[ $last == *dcv.pem* ]]; then touch "$STUB_DIR/trusted"
    elif [[ $last == *pcluster_dcv_connect* ]]; then
      [[ -f $STUB_DIR/notoken ]] || echo "{CONNECT_LINE}"
    fi ;;
  "ssm start-session") echo "forwarding" ;;
esac
"""
MKCERT = """#!/usr/bin/env bash
echo "mkcert $*" >> "$STUB_LOG"
while (( $# )); do
  [[ $1 == -cert-file ]] && echo "SIGNED CERTIFICATE" > "$2"
  [[ $1 == -csr ]] && cat "$2" >> "$STUB_LOG"
  shift
done
"""


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "aws").write_text(AWS)
    (bin_dir / "mkcert").write_text(MKCERT)
    (bin_dir / "open").write_text('#!/usr/bin/env bash\necho "open $*" >> "$STUB_LOG"\n')
    for stub in bin_dir.iterdir():
        stub.chmod(0o755)
    return bin_dir


def session(bin_dir: Path, *options: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "STUB_LOG": str(bin_dir.parent / "calls"),
        "STUB_DIR": str(bin_dir.parent),
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
    assert "mkcert" not in log
    assert "openssl" not in log


def test_trust_signs_a_key_the_node_made_and_keeps_there(bin_dir: Path) -> None:
    result = session(bin_dir, "-t")
    assert result.returncode == 0, result.stderr
    log = calls(bin_dir)
    assert "openssl req" in log
    assert "-keyout /etc/dcv/dcv.key" in log
    assert "subjectAltName=DNS:localhost,IP:127.0.0.1" in log
    assert "mkcert -csr" in log
    assert "BEGIN CERTIFICATE REQUEST" in log
    assert "SIGNED CERTIFICATE" in log
    assert "chmod 600 /etc/dcv/dcv.pem" in log
    assert "systemctl restart dcvserver" in log
    # The private key is made on the node and never travels.
    assert "dcv.key <<" not in log
    assert "PRIVATE KEY" not in log
    assert log.index("restart dcvserver") < log.index("pcluster_dcv_connect.sh")


def test_a_node_already_serving_localhost_is_left_alone(bin_dir: Path) -> None:
    (bin_dir.parent / "trusted").touch()
    result = session(bin_dir, "-t")
    assert result.returncode == 0, result.stderr
    log = calls(bin_dir)
    assert "s_client" in log
    assert "openssl req" not in log
    assert "restart dcvserver" not in log
    assert "mkcert -csr" not in log


def test_without_a_token_the_port_forward_is_closed(bin_dir: Path) -> None:
    (bin_dir.parent / "notoken").touch()
    result = session(bin_dir)
    assert result.returncode == 1
    assert "no session token" in result.stderr
    assert "open " not in calls(bin_dir)


def test_the_cluster_may_be_named(bin_dir: Path) -> None:
    result = session(bin_dir, "qec-arm")
    assert result.returncode == 0, result.stderr
    assert "parallelcluster:cluster-name,Values=qec-arm" in calls(bin_dir)


def test_trust_needs_mkcert(bin_dir: Path) -> None:
    """With only the stubs and the system directories on the path, there is no mkcert."""
    (bin_dir / "mkcert").unlink()
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "STUB_LOG": str(bin_dir.parent / "calls"),
    }
    result = subprocess.run(
        ["bash", SCRIPT, "-t"], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "mkcert" in result.stderr
