import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / ".claude" / "hooks"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run_hook(repo: Path, script: str, payload: Mapping[str, object], *args: str) -> int:
    return subprocess.run(
        [HOOKS / script, *args],
        cwd=repo,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(repo)},
        input=json.dumps({"tool_input": payload}),
        text=True,
        capture_output=True,
        check=False,
    ).returncode


def events(repo: Path) -> list[dict[str, object]]:
    log = repo / ".claude" / "metrics" / "events.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repo = tmp_path_factory.mktemp("project")
    for name in ("pyproject.toml", "uv.lock", ".python-version"):
        shutil.copy(ROOT / name, repo / name)
    (repo / ".pre-commit-config.yaml").write_text("repos: []\n")
    (repo / ".gitignore").write_text("scratch.txt\n.venv/\n")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "__init__.py").touch()
    (repo / "pkg" / "fine.py").write_text("ANSWER = 42\n")
    (repo / "pkg" / "broken.py").write_text("ANSWER = 41\n")
    (repo / "tests" / "pkg").mkdir(parents=True)
    (repo / "tests" / "__init__.py").touch()
    (repo / "tests" / "pkg" / "__init__.py").touch()
    (repo / "tests" / "pkg" / "test_fine.py").write_text(
        "from pkg.fine import ANSWER\n\n\ndef test_answer() -> None:\n    assert ANSWER == 42\n"
    )
    (repo / "tests" / "pkg" / "test_broken.py").write_text(
        "from pkg.broken import ANSWER\n\n\ndef test_answer() -> None:\n    assert ANSWER == 42\n"
    )
    (repo / "scratch.txt").write_text("ignored\n")
    git(repo, "init", "-q", "-b", "work")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "chore: seed")
    subprocess.run(["uv", "sync", "-q"], cwd=repo, check=True)
    return repo
