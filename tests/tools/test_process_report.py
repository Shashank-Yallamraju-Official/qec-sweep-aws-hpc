import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools.process_report import (
    Event,
    PlannedCommit,
    TaskStats,
    active_time,
    current_task,
    main,
    open_segment,
    read_events,
    read_plan,
    stats_per_commit,
    status_line,
    table,
)

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)


def at(minute: int) -> datetime:
    return T0 + timedelta(minutes=minute)


def ev(minute: int, kind: str, **data: object) -> Event:
    return Event(at=at(minute), kind=kind, data=data)


def test_read_events_skips_truncated_last_line(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"
    log.write_text(
        '{"ts": "2026-10-29T12:00:00Z", "event": "edit", "file": "a.py", "ok": true}\n'
        '{"ts": "2026-10-29T12:01:00Z", "event": "edit", "file": "b.py", "ok": false}\n'
        '{"ts": "2026-'
    )
    events = read_events(log)
    assert [e.kind for e in events] == ["edit", "edit"]
    assert events[1].data["ok"] is False


def test_read_events_missing_file(tmp_path: Path) -> None:
    assert read_events(tmp_path / "missing.jsonl") == []


def test_read_plan_groups_and_positions(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Plan\n\n## Commits\n\n### Bootstrap\n\n1. `chore: add licence`\n2. `build: add gate`\n\n"
        "### Stage 1, unit of work\n\n3. `feat(sweep): model a cell`\n"
    )
    assert read_plan(plan) == [
        PlannedCommit("Bootstrap", 1, "chore: add licence"),
        PlannedCommit("Bootstrap", 2, "build: add gate"),
        PlannedCommit("Stage 1, unit of work", 3, "feat(sweep): model a cell"),
    ]


PLAN = [
    PlannedCommit("Bootstrap", 1, "chore: a"),
    PlannedCommit("Bootstrap", 2, "build: b"),
    PlannedCommit("Stage 1", 3, "feat(sweep): c"),
]


def test_current_task_is_first_not_committed() -> None:
    assert current_task(PLAN, {"chore: a"}) == PLAN[1]


def test_current_task_none_when_plan_done() -> None:
    assert current_task(PLAN, {p.subject for p in PLAN}) is None


def test_active_time_excludes_long_gaps() -> None:
    times = [at(0), at(5), at(30), at(32)]
    assert active_time(times, idle_gap=timedelta(minutes=10)) == timedelta(minutes=7)


def test_active_time_single_event_is_zero() -> None:
    assert active_time([at(0)]) == timedelta(0)


EVENTS = [
    ev(0, "edit", ok=True),
    ev(1, "edit", ok=False),
    ev(2, "test", ok=False),
    ev(3, "commit_rejected"),
    ev(4, "edit", ok=True),
    ev(5, "commit", sha="aaa", subject="feat(sweep): a"),
    ev(6, "edit", ok=True),
    ev(7, "commit", sha="bbb", subject="feat(sweep): b"),
]


def test_stats_per_commit_splits_on_commit_events() -> None:
    a, b = stats_per_commit(EVENTS)
    assert a == TaskStats("feat(sweep): a", timedelta(minutes=5), 3, 1, 1, 1)
    assert b == TaskStats("feat(sweep): b", timedelta(minutes=2), 1, 0, 0, 0)


def test_open_segment_after_last_commit() -> None:
    events = [*EVENTS, ev(8, "edit", ok=False), ev(9, "edit", ok=True)]
    assert open_segment(events, "feat(sweep): c", now=at(12)) == TaskStats(
        "feat(sweep): c", timedelta(minutes=5), 2, 1, 0, 0
    )


def test_status_line_full() -> None:
    task = PlannedCommit("Stage 5, job array", 24, "feat(jobs): submit the grid as a slurm array")
    current = TaskStats(task.subject, timedelta(minutes=14, seconds=20), 6, 2, 0, 1)
    assert status_line("stage-05-jobs", task, 49, current) == (
        "stage-05-jobs  24/49 feat(jobs): submit the grid as a slurm array"
        "  14m · 6 edits · 2 rejected · 2 attempts"
    )


def test_status_line_without_plan_or_log() -> None:
    assert status_line("stage-05-jobs", None, 0, None) == "stage-05-jobs"


def test_table_markdown() -> None:
    rows = [TaskStats("feat(sweep): a", timedelta(minutes=5, seconds=40), 3, 1, 1, 1)]
    assert table(rows).splitlines() == [
        "| commit | active min | edits | edits rejected | tests failed | commit attempts |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        "| feat(sweep): a | 6 | 3 | 1 | 1 | 2 |",
    ]


def test_main_status_prints_branch_only_in_fresh_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q", "-b", "trunk"], cwd=tmp_path, check=True)
    commit = [*git, "commit", "-q", "--allow-empty", "-m", "chore: a"]
    subprocess.run(commit, cwd=tmp_path, check=True)
    assert main(["--status", "--repo", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "trunk"
