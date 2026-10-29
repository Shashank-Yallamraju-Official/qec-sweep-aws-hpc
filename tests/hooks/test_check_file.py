import shutil
from pathlib import Path

import pytest

from tests.hooks.conftest import events, run_hook


@pytest.fixture(autouse=True)
def clean_log(project: Path) -> None:
    shutil.rmtree(project / ".claude" / "metrics", ignore_errors=True)


def check(repo: Path, path: Path) -> int:
    return run_hook(repo, "check-file.sh", {"file_path": str(path)})


def test_ignores_paths_outside_the_repository(project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "note.md"
    outside.write_text("x")
    assert check(project, outside) == 0
    assert events(project) == []


def test_ignores_gitignored_files(project: Path) -> None:
    assert check(project, project / "scratch.txt") == 0
    assert events(project) == []


def test_runs_matching_test_for_absolute_source_path(project: Path) -> None:
    assert check(project, project / "pkg" / "fine.py") == 0
    assert [(e["event"], e["ok"]) for e in events(project)] == [("edit", True), ("test", True)]
    assert events(project)[0]["file"] == "pkg/fine.py"


def test_blocks_when_matching_test_fails(project: Path) -> None:
    assert check(project, project / "pkg" / "broken.py") == 2
    assert [(e["event"], e["ok"]) for e in events(project)] == [("edit", True), ("test", False)]


def test_runs_an_edited_test_file_itself(project: Path) -> None:
    assert check(project, project / "tests" / "pkg" / "test_broken.py") == 2
    assert [e["event"] for e in events(project)] == ["edit", "test"]
