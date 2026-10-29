from pathlib import Path

import pytest

from tests.hooks.conftest import git, run_hook


def guard(repo: Path, command: str) -> int:
    return run_hook(repo, "guard-git.sh", {"command": command})


@pytest.mark.parametrize(
    "command",
    [
        "git commit --no-verify -m x",
        "git commit -n -m x",
        "SKIP=ruff git commit -m x",
        "git -c core.hooksPath=/dev/null commit -m x",
        "git push --force",
        "git push --force-with-lease origin work",
        "git push origin +work",
        "git push origin HEAD -uf",
        "git switch main && git commit -m x",
        "git checkout main && git push",
        "(git commit --no-verify -m x)",
        "{ git push --force; }",
        "echo $(git commit --no-verify -m x)",
        "git commit --no-v -m x",
    ],
)
def test_refuses_bypasses(project: Path, command: str) -> None:
    assert guard(project, command) == 2


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git commit -m x",
        "git -c user.name=x commit -m x",
        "git push -u origin work",
        "git stash push -f",
        "grep -rn -- --no-verify docs/",
        'echo "git commit"',
        "ls",
    ],
)
def test_allows_ordinary_commands(project: Path, command: str) -> None:
    assert guard(project, command) == 0


def test_refuses_commit_and_push_on_main(project: Path) -> None:
    git(project, "switch", "-q", "-c", "main")
    try:
        assert guard(project, "git commit -m x") == 2
        assert guard(project, "git -c user.name=x commit -m x") == 2
        assert guard(project, "git push") == 2
        assert guard(project, "git status") == 0
        assert guard(project, "git switch -c topic && git commit -m x") == 0
        assert guard(project, "git checkout -b topic main && git commit -m x") == 0
        assert guard(project, "git checkout -- README.md && git commit -m x") == 2
        assert guard(project, "git switch -c topic && git switch main && git push") == 2
    finally:
        git(project, "switch", "-q", "work")
