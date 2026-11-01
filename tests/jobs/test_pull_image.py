import os
import ssl
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "jobs" / "pull-image.sh"
DIGEST = "sha256:" + "ab" * 32
SERVICE = "fake"


class Registry(BaseHTTPRequestHandler):
    """Enough of the OCI distribution API to answer a manifest HEAD behind a bearer token."""

    digest: str | None = DIGEST

    def do_HEAD(self) -> None:
        if self.headers.get("Authorization") != "Bearer secret":
            self.send_response(401)
            challenge = f'Bearer realm="https://{self.headers["Host"]}/token",service="{SERVICE}"'
            self.send_header("WWW-Authenticate", challenge + ',scope="repository:qec/sweep:pull"')
            self.end_headers()
            return
        self.send_response(200)
        if type(self).digest:
            self.send_header("Docker-Content-Digest", str(type(self).digest))
        self.end_headers()

    def do_GET(self) -> None:
        assert self.path.startswith(f"/token?service={SERVICE}&scope=repository:qec/sweep:pull")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"token": "secret"}')

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@dataclass(frozen=True)
class Node:
    """What the script finds on a node: an image URI, the registry's certificate, a PATH."""

    uri: str
    cert: Path
    bin_dir: Path


@pytest.fixture(scope="module")
def registry(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, Path]]:
    certs = tmp_path_factory.mktemp("certs")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
         "-keyout", certs / "key.pem", "-out", certs / "cert.pem",
         "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
        check=True,
        capture_output=True,
    )  # fmt: skip
    server = HTTPServer(("localhost", 0), Registry)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certs / "cert.pem", certs / "key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"oras://localhost:{server.server_port}/qec/sweep:abc", certs / "cert.pem"
    server.shutdown()


@pytest.fixture
def node(registry: tuple[str, Path], tmp_path: Path) -> Node:
    """A stand-in apptainer that writes the file it was asked for and logs the call."""
    stub = tmp_path / "bin" / "apptainer"
    stub.parent.mkdir()
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$@" >> "$APPTAINER_CALLS"\n'
        'echo "pulled" > "${@: -2:1}"\n'
        'echo "INFO:    Digest: $PULLED_DIGEST" >&2\n'
    )
    stub.chmod(0o755)
    uri, cert = registry
    return Node(uri, cert, stub.parent)


def pull(
    node: Node, cache: Path, digest: str = DIGEST, baked: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{node.bin_dir}:{os.environ['PATH']}",
        "CURL_CA_BUNDLE": str(node.cert),
        "APPTAINER_CALLS": str(cache / "calls"),
        "PULLED_DIGEST": digest,
    }
    args = [str(cache), str(baked)] if baked else [str(cache)]
    return subprocess.run(
        [SCRIPT, node.uri, *args], env=env, capture_output=True, text=True, check=False
    )


def calls(cache: Path) -> list[str]:
    log = cache / "calls"
    return log.read_text().splitlines() if log.exists() else []


def test_a_first_pull_lands_the_image_under_its_digest(node: Node, tmp_path: Path) -> None:
    cache = tmp_path / "images"
    result = pull(node, cache)
    assert result.returncode == 0, result.stderr
    sif = cache / f"{DIGEST.removeprefix('sha256:')}.sif"
    assert result.stdout == f"{DIGEST} {sif}\n"
    assert sif.read_text() == "pulled\n"
    assert len(calls(cache)) == 1
    assert calls(cache)[0].endswith(f" {node.uri}")


def test_a_second_pull_of_the_same_digest_reuses_the_file(node: Node, tmp_path: Path) -> None:
    cache = tmp_path / "images"
    assert pull(node, cache).returncode == 0
    result = pull(node, cache)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(DIGEST)
    assert len(calls(cache)) == 1
    assert not list(cache.glob(".*"))


def test_an_image_baked_into_the_node_is_used_without_a_pull(node: Node, tmp_path: Path) -> None:
    baked = tmp_path / "opt" / "images"
    baked.mkdir(parents=True)
    sif = baked / f"{DIGEST.removeprefix('sha256:')}.sif"
    sif.write_text("baked\n")
    result = pull(node, tmp_path / "images", baked=baked)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{DIGEST} {sif}\n"
    assert calls(tmp_path / "images") == []


def test_a_tag_that_moved_during_the_pull_is_refused(node: Node, tmp_path: Path) -> None:
    cache = tmp_path / "images"
    result = pull(node, cache, digest="sha256:" + "cd" * 32)
    assert result.returncode == 1
    assert "moved" in result.stderr
    assert not list(cache.glob("*.sif"))


def test_a_registry_that_names_no_digest_is_refused(node: Node, tmp_path: Path) -> None:
    Registry.digest = None
    try:
        result = pull(node, tmp_path / "images")
    finally:
        Registry.digest = DIGEST
    assert result.returncode == 1
    assert f"no digest for {node.uri}" in result.stderr
    assert calls(tmp_path / "images") == []
