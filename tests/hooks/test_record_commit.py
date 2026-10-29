import shutil
from pathlib import Path

import pytest

from tests.hooks.conftest import events, git, run_hook

COMMIT = {"command": "git commit -m x"}


@pytest.fixture(autouse=True)
def clean_log(project: Path) -> None:
    shutil.rmtree(project / ".claude" / "metrics", ignore_errors=True)


def test_logs_a_commit_that_moved_head(project: Path) -> None:
    run_hook(project, "record-commit.sh", COMMIT, "before")
    git(project, "commit", "-q", "--allow-empty", "-m", "feat(sweep): a")
    assert run_hook(project, "record-commit.sh", COMMIT, "after") == 0
    (event,) = events(project)
    assert event["event"] == "commit"
    assert event["subject"] == "feat(sweep): a"
    assert event["sha"] == git(project, "rev-parse", "HEAD").strip()


def test_logs_a_rejected_commit(project: Path) -> None:
    run_hook(project, "record-commit.sh", COMMIT, "before")
    assert run_hook(project, "record-commit.sh", COMMIT, "after") == 0
    assert [e["event"] for e in events(project)] == ["commit_rejected"]


def test_ignores_commands_that_do_not_commit(project: Path) -> None:
    run_hook(project, "record-commit.sh", {"command": "git status"}, "before")
    run_hook(project, "record-commit.sh", {"command": "git status"}, "after")
    assert events(project) == []


@pytest.mark.parametrize(
    "command", ['echo "git commit"', "cat <<EOF\nmentioned 'git commit' in prose\nEOF"]
)
def test_ignores_commands_that_only_mention_a_commit(project: Path, command: str) -> None:
    run_hook(project, "record-commit.sh", {"command": command}, "before")
    run_hook(project, "record-commit.sh", {"command": command}, "after")
    assert events(project) == []


def test_logs_every_commit_a_command_makes(project: Path) -> None:
    run_hook(project, "record-commit.sh", COMMIT, "before")
    git(project, "commit", "-q", "--allow-empty", "-m", "feat(sweep): first")
    git(project, "commit", "-q", "--allow-empty", "-m", "feat(sweep): second")
    run_hook(project, "record-commit.sh", COMMIT, "after")
    assert [e["subject"] for e in events(project)] == ["feat(sweep): first", "feat(sweep): second"]


def test_logs_every_commit_when_there_was_no_head(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "work")
    run_hook(tmp_path, "record-commit.sh", COMMIT, "before")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: first")
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "chore: second")
    run_hook(tmp_path, "record-commit.sh", COMMIT, "after")
    assert [e["subject"] for e in events(tmp_path)] == ["chore: first", "chore: second"]


@pytest.mark.parametrize("line", ["git -c user.name=x commit -m y", "(git commit -m y)"])
def test_logs_a_commit_with_global_options_or_in_a_subshell(project: Path, line: str) -> None:
    command = {"command": line}
    run_hook(project, "record-commit.sh", command, "before")
    git(project, "commit", "-q", "--allow-empty", "-m", "feat(sweep): b")
    run_hook(project, "record-commit.sh", command, "after")
    assert [e["event"] for e in events(project)] == ["commit"]
