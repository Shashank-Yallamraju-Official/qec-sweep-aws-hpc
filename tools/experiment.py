"""Experiment records: ``experiment new``, ``check`` and ``index``.

A record is one Markdown file under ``experiments/``, numbered, its data in a
frontmatter block and its prose under nine fixed headings in a fixed order; the
process that fills it is the directory's README. ``new`` writes the next record
from the template; ``check`` refuses a record that lacks a field or a heading, a
closed one without its result, and a closed one whose Prediction differs from the
one in the commit that registered the record, which is the proof the prediction came
first and survives the rebase that merging rewrites commit ids with; ``index``
rewrites the table in the README from the records' frontmatter, and ``check``
fails while that table is stale.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "experiments" / "TEMPLATE.md"
README = "README.md"
RECORD = re.compile(r"^(?P<id>\d{2})-[a-z0-9-]+\.md$")
HEADINGS = (
    "Question",
    "State",
    "Diagnosis",
    "Candidates",
    "Decision",
    "Prediction",
    "Run",
    "Result",
    "Next",
)
FIELDS = (
    "id",
    "title",
    "status",
    "process",
    "runs",
    "commits",
    "pull_request",
    "cost_usd",
    "outcome",
    "next",
)
STATUSES = frozenset({"registered", "running", "closed"})
OUTCOMES = frozenset({"supported", "refuted", "inconclusive"})
CLOSED_SECTIONS = ("Run", "Result", "Next")
INDEX_START, INDEX_END = "<!-- index -->", "<!-- /index -->"
INDEX_HEADER = (
    "| Experiment | Title | Status | Outcome | Cost (USD) | Next |",
    "| --- | --- | --- | --- | --- | --- |",
)
REVISION = re.compile(r"^\| (\d+) \|", re.MULTILINE)

Value = str | int | float | list[str] | None


@dataclass(frozen=True)
class Record:
    """One experiment record as its file holds it.

    Attributes:
        path: The file.
        fields: The frontmatter, by key.
        headings: The second-level headings, in the order they appear.
        sections: The prose under each heading, stripped.
    """

    path: Path
    fields: dict[str, Value]
    headings: tuple[str, ...]
    sections: dict[str, str]

    @property
    def id(self) -> int:
        """The record's number."""
        return int(str(self.fields.get("id")))

    @property
    def title(self) -> str:
        """What the experiment is called."""
        return str(self.fields.get("title"))

    @property
    def status(self) -> str:
        """``registered``, ``running`` or ``closed``."""
        return str(self.fields.get("status"))

    @property
    def process(self) -> int:
        """The version of the process the record followed."""
        return int(str(self.fields.get("process")))

    @property
    def commits(self) -> list[str]:
        """The commits of the run, as the frontmatter lists them."""
        value = self.fields.get("commits")
        return list(value) if isinstance(value, list) else []


def read_record(path: Path) -> Record:
    """Parse a record's frontmatter and headings.

    Raises:
        ValueError: When the file does not open with a frontmatter block.
    """
    text = path.read_text()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not match:
        msg = f"{path.name} does not start with a frontmatter block"
        raise ValueError(msg)
    fields = {k: _value(v) for k, _, v in (line.partition(":") for line in match[1].splitlines())}
    parts = re.split(r"^## (.+)$", match[2], flags=re.MULTILINE)
    headings = tuple(parts[1::2])
    sections = dict(zip(headings, (body.strip() for body in parts[2::2]), strict=True))
    return Record(path, fields, headings, sections)


def _value(raw: str) -> Value:
    raw = raw.strip()
    if raw == "null":
        return None
    if raw.startswith("[") and raw.endswith("]"):
        return [item.strip() for item in raw[1:-1].split(",") if item.strip()]
    for kind in (int, float):
        try:
            return kind(raw)
        except ValueError:
            continue
    return raw


def records(directory: Path) -> list[Path]:
    """Every record file under the directory, by number."""
    return sorted(p for p in directory.glob("*.md") if RECORD.match(p.name))


def new(directory: Path, slug: str) -> Path:
    """Write the next record from the template and return its path.

    The title is the slug with its dashes made spaces; the process version is the
    highest in the README's revisions table, or 1 without one.
    """
    existing = records(directory)
    number = 1 + max((int(RECORD.match(p.name)["id"]) for p in existing), default=0)  # type: ignore[index]
    readme = directory / README
    versions = REVISION.findall(readme.read_text()) if readme.exists() else []
    path = directory / f"{number:02d}-{slug}.md"
    path.write_text(
        TEMPLATE.read_text().format(
            id=number,
            title=slug.replace("-", " ").capitalize(),
            process=max(map(int, versions), default=1),
        )
    )
    return path


def index(directory: Path) -> Path:
    """Rewrite the README's index table from the records and return the README's path."""
    readme = directory / README
    text = readme.read_text()
    start, end = text.index(INDEX_START) + len(INDEX_START), text.index(INDEX_END)
    readme.write_text(text[:start] + "\n" + _index_table(directory) + "\n" + text[end:])
    return readme


def _index_table(directory: Path) -> str:
    rows = []
    for path in records(directory):
        try:
            r = read_record(path)
        except ValueError:
            continue
        cost = r.fields.get("cost_usd")
        rows.append(
            f"| [{r.id:02d}]({path.name}) | {r.title} | {r.status} | "
            f"{r.fields.get('outcome') or '-'} | {'-' if cost is None else cost} | "
            f"{r.fields.get('next') or '-'} |"
        )
    return "\n".join([*INDEX_HEADER, *rows])


def check(directory: Path) -> list[str]:
    """Every problem with the records and the index under a directory; empty when none."""
    readme = directory / README
    if not readme.exists() or INDEX_START not in readme.read_text():
        return [f"{README} with an index block is missing"]
    problems: list[str] = []
    parsed: dict[Path, Record] = {}
    for path in records(directory):
        try:
            parsed[path] = read_record(path)
        except ValueError as error:
            problems.append(f"{path.name}: {error}")
    ids = {r.id for r in parsed.values() if isinstance(r.fields.get("id"), int)}
    seen: dict[int, str] = {}
    for path, record in parsed.items():
        problems.extend(f"{path.name}: {p}" for p in _check_record(record, seen))
        problems.extend(f"{path.name}: {p}" for p in _check_next(record, ids))
    text = readme.read_text()
    start, end = text.index(INDEX_START) + len(INDEX_START), text.index(INDEX_END)
    if text[start:end].strip() != _index_table(directory):
        problems.append(f"{README}: the index is stale; run experiment index")
    return problems


def _check_next(record: Record, ids: set[int]) -> list[str]:
    successor = record.fields.get("next")
    if successor is None:
        return []
    if not isinstance(successor, int):
        return [f"next names '{successor}', which is no record number"]
    return [] if successor in ids else [f"next names {successor:02d}, which is no record"]


def _check_record(record: Record, seen: dict[int, str]) -> list[str]:
    path = record.path
    problems = [f"{f} is missing from the frontmatter" for f in FIELDS if f not in record.fields]
    if problems:
        return problems
    if record.id != int(RECORD.match(path.name)["id"]):  # type: ignore[index]
        problems.append(f"id {record.id} does not match the file's number")
    if record.id in seen:
        problems.append(f"id {record.id} is also {seen[record.id]}")
    seen[record.id] = path.name
    if record.status not in STATUSES:
        problems.append(f"status '{record.status}' is not one of {', '.join(sorted(STATUSES))}")
    problems.extend(_check_headings(record))
    if record.status == "closed":
        problems.extend(_check_closed(record))
    return problems


def _check_headings(record: Record) -> list[str]:
    for expected, found in zip(HEADINGS, record.headings, strict=False):
        if expected != found:
            return [f"heading '{expected}' is missing or out of order; found '{found}'"]
    if len(record.headings) != len(HEADINGS):
        missing = HEADINGS[len(record.headings) :] or record.headings[len(HEADINGS) :]
        return [f"heading '{missing[0]}' is missing or out of order"]
    return []


def _check_closed(record: Record) -> list[str]:
    problems = []
    if record.fields.get("outcome") not in OUTCOMES:
        problems.append(f"a closed record's outcome is one of {', '.join(sorted(OUTCOMES))}")
    if record.fields.get("cost_usd") is None:
        problems.append("a closed record's cost_usd is a number")
    problems.extend(f"{s} is empty" for s in CLOSED_SECTIONS if not record.sections.get(s))
    if not record.commits:
        problems.append("a closed record's commits name the run's commits")
        return problems
    registered = _register_commit(record.path)
    if registered is None:
        problems.append(
            "the record was never committed, so nothing proves its prediction came first"
        )
        return problems
    then = _registered_prediction(record.path, registered)
    if then != record.sections.get("Prediction", ""):
        problems.append(
            f"the Prediction changed since the record was registered in {registered[:7]}"
        )
    return problems


def _register_commit(path: Path) -> str | None:
    output = _git(path.parent, "log", "--diff-filter=A", "--format=%H", "--follow", "--", path.name)
    return output.splitlines()[-1] if output else None


def _registered_prediction(path: Path, commit: str) -> str:
    # Read relative to the records' directory, so the proof survives a rebase that
    # rewrites every commit id but not what the register commit holds at that path.
    text = _git(path.parent, "show", f"{commit}:./{path.name}")
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    sections = dict(zip(parts[1::2], (body.strip() for body in parts[2::2]), strict=True))
    return str(sections.get("Prediction", ""))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, check=False, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def main(argv: Sequence[str] | None = None) -> int:
    """Run one of ``new <slug>``, ``check`` or ``index`` from the command line.

    Args:
        argv: The subcommand and its arguments; ``None`` reads ``sys.argv``. ``--dir``
            names the records' directory, ``experiments`` by default.

    Returns:
        Exit status: 0 when done or when the check passes, 1 when it finds problems.
    """
    parser = argparse.ArgumentParser(prog="experiment", description="experiment records")
    where = argparse.ArgumentParser(add_help=False)
    where.add_argument("--dir", type=Path, default=Path("experiments"), help="the records")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("new", parents=[where], help="write the next record").add_argument("slug")
    commands.add_parser("check", parents=[where], help="refuse incomplete records, stale index")
    commands.add_parser("index", parents=[where], help="rewrite the README's index")
    args = parser.parse_args(argv)
    if args.command == "new":
        print(new(args.dir, args.slug))
    elif args.command == "index":
        print(index(args.dir))
    else:
        problems = check(args.dir)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
