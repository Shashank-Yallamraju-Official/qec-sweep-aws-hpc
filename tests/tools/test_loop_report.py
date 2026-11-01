from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from results.run import read_cells, read_record
from results.store import LocalStore
from tests.tools.fakes import (
    BUILT,
    COMMITTED,
    FIRST,
    GITHUB,
    IMAGE,
    REPOSITORY,
    SHA,
    SUBMITTED,
    fetch,
    write_run,
)
from tools.loop_report import (
    ImageRef,
    Loop,
    first_cell,
    image_built_at,
    main,
    parse_image,
    report,
    time_loop,
)

LOOP = Loop(
    run="20261031T002000Z",
    commit=SHA,
    committed=COMMITTED,
    image_built=BUILT,
    submitted=SUBMITTED,
    first_cell=FIRST,
)


def test_parse_image_takes_the_name_and_commit_from_the_tag() -> None:
    assert parse_image(IMAGE) == ImageRef(name="sweep", commit=SHA)


def test_parse_image_refuses_a_tag_that_is_not_a_commit() -> None:
    with pytest.raises(ValueError, match="latest is not a commit"):
        parse_image("oras://ghcr.io/example/qec/sweep:latest")


def test_first_cell_is_the_earliest_start(tmp_path: Path) -> None:
    key = write_run(tmp_path)
    assert first_cell(read_cells(LocalStore(tmp_path), key)) == FIRST


def test_image_built_at_names_a_commit_with_no_image_run() -> None:
    def no_runs(path: str) -> Any:  # noqa: ANN401
        return {"workflow_runs": []} if "actions/runs" in path else GITHUB[path]

    with pytest.raises(ValueError, match=f"no image workflow run built {SHA[:7]}"):
        image_built_at(no_runs, REPOSITORY, ImageRef("sweep", SHA))


def test_time_loop_splits_the_loop_into_its_phases(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    key = write_run(tmp_path)
    loop = time_loop(read_record(store, key), read_cells(store, key), fetch, REPOSITORY)
    assert loop == LOOP
    assert loop.build == timedelta(seconds=77)
    assert loop.wait == timedelta(minutes=7, seconds=8)
    assert loop.cluster == timedelta(minutes=5)
    assert loop.total == timedelta(minutes=13, seconds=25)


def test_report_prints_each_phase_in_minutes() -> None:
    text = report(LOOP)
    assert "20261031T002000Z: commit 0d0eebc to its first cell in 13.4 min" in text
    assert "  commit to image built: 1.3 min" in text
    assert "  image built to submission: 7.1 min" in text
    assert "  submission to first cell: 5.0 min" in text


def test_main_times_a_run_by_address(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    key = write_run(tmp_path)
    assert main([str(tmp_path / key), "--repository", REPOSITORY], fetch=fetch) == 0
    assert "to its first cell in 13.4 min" in capsys.readouterr().out


def test_main_reports_a_run_with_no_cells(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    key = write_run(tmp_path)
    for cell in (tmp_path / key).glob("*.parquet"):
        cell.unlink()
    assert main([str(tmp_path / key), "--repository", REPOSITORY], fetch=fetch) == 2
    assert "no cells under" in capsys.readouterr().err
