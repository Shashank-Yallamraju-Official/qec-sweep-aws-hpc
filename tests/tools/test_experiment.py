import json
import subprocess
from pathlib import Path

import pytest

from tests.results.conftest import FULL_RECORD, write_run
from tools.experiment import (
    HEADINGS,
    Baseline,
    baseline,
    check,
    describe,
    index,
    main,
    new,
    read_record,
)

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


def _register(repo: Path) -> None:
    index(repo / "experiments")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs(experiments): register")


def test_a_prediction_changed_after_registration_is_a_problem(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    _register(repo)
    path.write_text(
        path.read_text().replace("## Prediction\n", "## Prediction\n\nMoved the goalposts.\n")
    )
    _close(path, "0" * 40)
    index(repo / "experiments")
    (problem,) = check(repo / "experiments")
    assert "Prediction" in problem


def test_a_closed_record_whose_prediction_is_unchanged_passes(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    path.write_text(path.read_text().replace("## Prediction\n", "## Prediction\n\nIt falls.\n"))
    _register(repo)
    _close(path, "0" * 40)
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


def test_a_malformed_record_is_reported_not_raised(repo: Path) -> None:
    new(repo / "experiments", "learning-curve")
    (repo / "experiments" / "02-broken.md").write_text("# no frontmatter\n")
    index(repo / "experiments")
    problems = check(repo / "experiments")
    assert any("02-broken.md" in p and "frontmatter" in p for p in problems)


def test_next_must_name_a_record_by_number(repo: Path) -> None:
    path = new(repo / "experiments", "learning-curve")
    path.write_text(path.read_text().replace("next: null", "next: 02-residual"))
    index(repo / "experiments")
    (problem,) = check(repo / "experiments")
    assert "next" in problem


def test_a_record_missing_a_field_is_still_a_target_for_next(repo: Path) -> None:
    first = new(repo / "experiments", "learning-curve")
    second = new(repo / "experiments", "residual-decoder")
    first.write_text(first.read_text().replace("next: null", "next: 2"))
    second.write_text(second.read_text().replace("cost_usd: null\n", ""))
    index(repo / "experiments")
    problems = check(repo / "experiments")
    assert len(problems) == 1
    assert "cost_usd" in problems[0]


def _manifest(models: Path, noise_model: str, run: str, name: str = "pymatching") -> None:
    models.mkdir(exist_ok=True)
    fields = {"name": name, "decoder": "pymatching", "noise_model": noise_model}
    fields |= {"run": run, "image_digest": "sha256:9d217f8c"}
    (models / f"{noise_model}.json").write_text(json.dumps(fields))


def test_baseline_names_the_decoder_in_force_and_the_chain_behind_it(tmp_path: Path) -> None:
    chain = f"{tmp_path.as_posix()}/chains/20261104T023950Z"
    judged = {
        **FULL_RECORD,
        "run": "20261104T023953Z",
        "noise": "correlated",
        "cells": ["5:0.001", "5:0.005"],
        "parents": [chain, f"{tmp_path.as_posix()}/train/20261104T023952Z"],
    }
    write_run(tmp_path, "evaluations/20261104T023953Z", judged, {5: 12})
    write_run(tmp_path, "sweeps/20261101T172143Z", FULL_RECORD, {3: 28})
    models = tmp_path / "models"
    _manifest(models, "correlated", f"{tmp_path}/evaluations/20261104T023953Z")
    _manifest(models, "depolarising", f"{tmp_path}/sweeps/20261101T172143Z")
    found = baseline(models)
    assert [b.noise_model for b in found] == ["correlated", "depolarising"]
    assert found[0].chain == chain
    assert found[0].cells == ("5:0.001", "5:0.005")
    assert found[1].chain is None
    text = describe(found)
    assert f"start from: uv run decoder-diagnose {chain}" in text
    assert "depolarising: pymatching in force from" in text
    assert "stands alone" in text


def test_baseline_main_prints_and_reports_a_missing_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    models = tmp_path / "models"
    assert main(["baseline", "--models", str(models)]) == 2
    assert capsys.readouterr().err.startswith("experiment: no manifests")
    _manifest(models, "correlated", f"{tmp_path}/evaluations/nowhere")
    assert main(["baseline", "--models", str(models)]) == 2
    assert "Traceback" not in capsys.readouterr().err
    write_run(tmp_path, "sweeps/20261101T172143Z", FULL_RECORD, {3: 28})
    _manifest(models, "correlated", f"{tmp_path}/sweeps/20261101T172143Z")
    assert main(["baseline", "--models", str(models)]) == 0
    assert describe([Baseline("correlated", "pymatching", "x", (), None)]).startswith(
        "correlated: pymatching in force from x"
    )
