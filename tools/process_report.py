"""Turns the hook event log into time and fix counts per planned commit.

Used by the Claude Code status line (--status), pull request bodies
(--stage) and the README process table (no flag).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

IDLE_GAP = timedelta(minutes=10)
EVENTS_PATH = Path(".claude/metrics/events.jsonl")
PLAN_PATH = Path("docs/plan.md")
GROUP = re.compile(r"^### (?P<group>.+)$")
PLANNED = re.compile(r"^(?P<position>\d+)\. `(?P<subject>.+)`$")


@dataclass(frozen=True)
class Event:
    """One line of the event log written by the Claude Code hooks.

    Attributes:
        at: When it happened.
        kind: ``edit``, ``test``, ``commit``, ``commit_rejected`` or ``session``.
        data: The remaining fields of the line, such as ``file``, ``ok`` or ``subject``.
    """

    at: datetime
    kind: str
    data: Mapping[str, object]


@dataclass(frozen=True)
class PlannedCommit:
    """One numbered commit from the plan, with the group heading it sits under."""

    group: str
    position: int
    subject: str


@dataclass(frozen=True)
class TaskStats:
    """What it took to land one commit: time, edits, and how often the gate said no."""

    subject: str
    active: timedelta
    edits: int
    rejected_edits: int
    failed_tests: int
    rejected_commits: int


def read_events(path: Path) -> list[Event]:
    """Read the event log, skipping any line that is not a well-formed event.

    A missing file and a line truncated by a crash both yield fewer events, never an error.
    """
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        try:
            record = json.loads(line)
            at = datetime.fromisoformat(record.pop("ts"))
            kind = str(record.pop("event"))
        except (ValueError, KeyError, AttributeError, TypeError):
            continue
        events.append(Event(at=at, kind=kind, data=record))
    return events


def read_plan(path: Path) -> list[PlannedCommit]:
    """Read the numbered commits of ``docs/plan.md`` under their ``###`` headings."""
    if not path.exists():
        return []
    plan = []
    group = ""
    for line in path.read_text().splitlines():
        if heading := GROUP.match(line):
            group = heading["group"]
        elif planned := PLANNED.match(line):
            plan.append(PlannedCommit(group, int(planned["position"]), planned["subject"]))
    return plan


def committed_subjects(repo: Path) -> set[str]:
    """Subject lines of every commit reachable from HEAD."""
    return set(_git(repo, "log", "--format=%s").splitlines())


def current_branch(repo: Path) -> str:
    """Name of the checked-out branch."""
    return _git(repo, "branch", "--show-current").strip()


def current_task(plan: Sequence[PlannedCommit], done: AbstractSet[str]) -> PlannedCommit | None:
    """The first planned commit whose subject is not yet in the history, if any."""
    return next((p for p in plan if p.subject not in done), None)


def active_time(times: Sequence[datetime], idle_gap: timedelta = IDLE_GAP) -> timedelta:
    """Time spanned by the timestamps, leaving out any gap longer than ``idle_gap``.

    A break for lunch or overnight should not count against the task it interrupted.
    """
    gaps = (later - earlier for earlier, later in pairwise(times))
    return sum((gap for gap in gaps if gap <= idle_gap), timedelta(0))


def stats_per_commit(events: Sequence[Event]) -> list[TaskStats]:
    """Statistics for each ``commit`` event, over the events since the previous one.

    A task is taken to start when the previous commit landed, so that commit's
    timestamp opens the next segment.
    """
    rows = []
    start = 0
    for index, event in enumerate(events):
        if event.kind == "commit":
            segment = events[max(start - 1, 0) : index + 1]
            rows.append(_stats(str(event.data.get("subject", "")), segment))
            start = index + 1
    return rows


def open_segment(events: Sequence[Event], subject: str, now: datetime) -> TaskStats:
    """Statistics for the task in progress: everything since the last commit, up to ``now``."""
    last_commit = max((i for i, e in enumerate(events) if e.kind == "commit"), default=-1)
    segment = events[max(last_commit, 0) :]
    return _stats(subject, segment, now)


def _stats(subject: str, segment: Sequence[Event], now: datetime | None = None) -> TaskStats:
    times = [e.at for e in segment] + ([now] if now else [])
    edits = [e for e in segment if e.kind == "edit"]
    tests = [e for e in segment if e.kind == "test"]
    return TaskStats(
        subject=subject,
        active=active_time(times),
        edits=len(edits),
        rejected_edits=sum(1 for e in edits if not e.data.get("ok", True)),
        failed_tests=sum(1 for e in tests if not e.data.get("ok", True)),
        rejected_commits=sum(1 for e in segment if e.kind == "commit_rejected"),
    )


def status_line(
    branch: str, task: PlannedCommit | None, total: int, current: TaskStats | None
) -> str:
    """One line for the Claude Code status bar: branch, next task, and the task's numbers so far.

    Unknown parts are left out: no plan drops the task, no event log drops the numbers.
    """
    parts = [branch]
    if task:
        parts.append(f"{task.position}/{total} {task.subject}")
    if current:
        parts.append(
            f"{_minutes(current.active)}m · {current.edits} edits · "
            f"{current.rejected_edits} rejected · {current.rejected_commits + 1} attempts"
        )
    return "  ".join(parts)


def table(rows: Sequence[TaskStats]) -> str:
    """Markdown table of the rows, one commit per line, for pull request bodies and the README."""
    lines = [
        "| commit | active min | edits | edits rejected | tests failed | commit attempts |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines += [
        f"| {r.subject} | {_minutes(r.active)} | {r.edits} | {r.rejected_edits} "
        f"| {r.failed_tests} | {r.rejected_commits + 1} |"
        for r in rows
    ]
    return "\n".join(lines)


def _minutes(duration: timedelta) -> int:
    return round(duration.total_seconds() / 60)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _status(repo: Path, plan: Sequence[PlannedCommit], events: Sequence[Event]) -> str:
    task = current_task(plan, committed_subjects(repo))
    current = open_segment(events, task.subject if task else "", datetime.now(UTC))
    return status_line(current_branch(repo), task, len(plan), current if events and plan else None)


def stage_rows(
    plan: Sequence[PlannedCommit], events: Sequence[Event], stage: str | None
) -> list[TaskStats]:
    """A fix commit belongs to the stage of the planned commit before it."""
    groups = {p.subject: p.group for p in plan}
    rows = []
    group = ""
    for row in stats_per_commit(events):
        group = groups.get(row.subject, group)
        if stage is None or group.lower().startswith(stage.lower()):
            rows.append(row)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    """Print the status line (``--status``) or a table, optionally for one plan group.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        Exit status 0. A missing or damaged log or plan yields less output rather than
        an error; a directory that is not a git repository still raises.
    """
    parser = argparse.ArgumentParser(description="time and fixes per commit from the hook log")
    parser.add_argument("--status", action="store_true", help="one line for the status bar")
    parser.add_argument("--stage", help="only commits whose plan group starts with this")
    parser.add_argument("--repo", type=Path, default=Path(), help="repository to read from")
    args = parser.parse_args(argv)
    plan = read_plan(args.repo / PLAN_PATH)
    events = read_events(args.repo / EVENTS_PATH)
    if args.status:
        print(_status(args.repo, plan, events))
    else:
        print(table(stage_rows(plan, events, args.stage)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
