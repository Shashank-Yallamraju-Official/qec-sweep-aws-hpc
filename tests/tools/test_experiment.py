import subprocess
from pathlib import Path

import pytest

from tools.experiment import HEADINGS, check, index, main, new, read_record

README = """# experiments

<!-- index -->
<!-- /index -->

## Revisions

| Version | Date | Change | Prompted by |
| --- | --- | --- | --- |
| 1 | 2026-11-03 | The loop as first written | stage 16 |
| 2 | 2026-11-04 | Costs stated per chain | 01 |
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"chore: {name}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "experiments").mkdir()
    (tmp_path / "experiments" / "README.md").write_text(README)
    return tmp_path


def test_new_numbers_the_record_and_fills_the_template(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    assert path.name == "01-learning-curve.md"
    record = read_record(path)
    assert record.id == 1
    assert record.title == "Learning curve"
    assert record.status == "registered"
    assert record.process == 2
    assert record.headings == HEADINGS


def test_new_counts_on_from_the_highest_record(repo: Path) -> None:
    new(repo / "experiments", "learning-curve")
    assert new(repo / "experiments", "residual-decoder").name == "02-residual-decoder.md"


def test_a_fresh_record_with_a_current_index_passes(repo: Path) -> None:
    new(repo / "experiments", "learning-curve")
    index(repo / "experiments")
    assert check(repo / "experiments") == []


def test_a_stale_index_is_a_problem(repo: Path) -> None:
    new(repo / "experiments", "learning-curve")
    (problem,) = check(repo / "experiments")
    assert "index" in problem


def test_index_writes_one_row_per_record_between_the_marks(repo: Path) -> None:
    new(repo / "experiments", "learning-curve")
    new(repo / "experiments", "residual-decoder")
    index(repo / "experiments")
    text = (repo / "experiments" / "README.md").read_text()
    assert "| [01](01-learning-curve.md) | Learning curve | registered |" in text
    assert "| [02](02-residual-decoder.md) | Residual decoder | registered |" in text
    assert text.endswith("| 2 | 2026-11-04 | Costs stated per chain | 01 |\n")


def test_a_heading_out_of_order_is_a_problem(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    text = (
        path.read_text()
        .replace("## Diagnosis\n", "")
        .replace("## Result\n", "## Result\n\n## Diagnosis\n")
    )
    path.write_text(text)
    index(repo / "experiments")
    (problem,) = check(repo / "experiments")
    assert "Diagnosis" in problem


def test_a_closed_record_needs_outcome_cost_result_and_commits(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    path.write_text(path.read_text().replace("status: registered", "status: closed"))
    index(repo / "experiments")
    problems = check(repo / "experiments")
    assert any("outcome" in p for p in problems)
    assert any("cost_usd" in p for p in problems)
    assert any("Result" in p for p in problems)
    assert any("commits" in p for p in problems)


def _close(path: Path, *commits: str) -> None:
    text = path.read_text()
    text = text.replace("status: registered", "status: closed")
    text = text.replace("commits: []", "commits: [" + ", ".join(commits) + "]")
    text = text.replace("cost_usd: null", "cost_usd: 1.5").replace(
        "outcome: null", "outcome: refuted"
    )
    text = text.replace("## Run\n", "## Run\n\nThree chains.\n")
    text = text.replace("## Result\n", "## Result\n\nFlat.\n").replace(
        "## Next\n", "## Next\n\nCapacity.\n"
    )
    path.write_text(text)


def test_a_run_commit_before_the_register_commit_is_a_problem(repo: Path) -> None:
    before = _commit(repo, "earlier")
    path = new(repo / "experiments", "learning-curve")
    index(repo / "experiments")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs(experiments): register")
    _close(path, before)
    index(repo / "experiments")
    (problem,) = check(repo / "experiments")
    assert "before" in problem
    assert before[:7] in problem


def test_a_run_commit_after_the_register_commit_passes(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    index(repo / "experiments")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs(experiments): register")
    after = _commit(repo, "the run")
    _close(path, after)
    index(repo / "experiments")
    assert check(repo / "experiments") == []


def test_a_closed_record_never_committed_is_a_problem(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    _close(path, "0" * 40)
    index(repo / "experiments")
    assert any("never committed" in p for p in check(repo / "experiments"))


def test_main_checks_and_reports(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["new", "learning-curve", "--dir", str(repo / "experiments")]) == 0
    assert main(["check", "--dir", str(repo / "experiments")]) == 1
    assert "index" in capsys.readouterr().out
    assert main(["index", "--dir", str(repo / "experiments")]) == 0
    assert main(["check", "--dir", str(repo / "experiments")]) == 0
