import subprocess
from pathlib import Path

import pytest

from tools.check_commit import check, main

GOOD = "feat(sweep): write a cell result as parquet named by cell"


def test_accepts_planned_subject() -> None:
    assert check(GOOD) == []


def test_accepts_type_without_scope() -> None:
    assert check("chore: add licence, gitignore and editor config") == []


def test_rejects_unknown_type() -> None:
    (problem,) = check("feature(sweep): add x")
    assert "type" in problem


def test_rejects_unknown_scope() -> None:
    (problem,) = check("feat(core): add x")
    assert "scope" in problem


def test_rejects_missing_colon_space() -> None:
    assert len(check("feat(sweep):add x")) == 1


def test_rejects_capitalised_subject() -> None:
    (problem,) = check("feat(sweep): Add x")
    assert "lowercase" in problem


def test_rejects_full_stop() -> None:
    (problem,) = check("feat(sweep): add x.")
    assert "full stop" in problem


def test_rejects_non_imperative() -> None:
    (problem,) = check("feat(sweep): added x")
    assert "imperative" in problem


def test_rejects_placeholder_subject() -> None:
    (problem,) = check("chore: wip")
    assert "says nothing" in problem


def test_subject_limit_boundary() -> None:
    prefix = "feat(sweep): add "
    at_limit = prefix + "x" * (60 - len(prefix))
    assert len(at_limit) == 60
    assert check(at_limit) == []
    (problem,) = check(at_limit + "x")
    assert "60" in problem


def test_requires_blank_line_before_body() -> None:
    (problem,) = check("feat(sweep): add x\nbody")
    assert "blank line" in problem


def test_rejects_long_body_line() -> None:
    (problem,) = check("feat(sweep): add x\n\n" + "w" * 73)
    assert "72" in problem


def test_rejects_trailer() -> None:
    (problem,) = check("feat(sweep): add x\n\nCo-Authored-By: a <a@b>")
    assert "trailer" in problem


def test_ignores_comment_lines() -> None:
    assert check("feat(sweep): add x\n# comment\n#\n") == []


def test_main_reads_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("Added stuff\n")
    assert main([str(message)]) == 1
    assert "type" in capsys.readouterr().out
    message.write_text(GOOD + "\n")
    assert main([str(message)]) == 0


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _commit(repo: Path, subject: str) -> None:
    (repo / "f").write_text(subject)
    _git(repo, "add", "f")
    _git(repo, "commit", "-q", "-m", subject)


def test_main_checks_range(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    _commit(tmp_path, "chore: add licence, gitignore and editor config")
    _commit(tmp_path, "build: add pre-commit with ruff, mypy and commit lint")
    _commit(tmp_path, "Added stuff")
    assert main(["--range", "HEAD~2..HEAD", "--repo", str(tmp_path)]) == 1
    _commit(tmp_path, GOOD)
    assert main(["--range", "HEAD~1..HEAD", "--repo", str(tmp_path)]) == 0


@pytest.mark.parametrize(
    "body",
    [
        "Reason: the bucket name must be globally unique.",
        "See: https://example.com/why",
        "Before: 5s. After: 2s.",
    ],
)
def test_accepts_one_line_body_that_looks_like_a_label(body: str) -> None:
    assert check(f"feat(sweep): add x\n\n{body}") == []


@pytest.mark.parametrize("trailer", ["Signed-off-by: a <a@b>", "Fixes: #12", "Change-Id: I0"])
def test_rejects_known_trailers(trailer: str) -> None:
    (problem,) = check(f"feat(sweep): add x\n\n{trailer}")
    assert "trailer" in problem
