"""Checks a commit message against the repository's format.

Used as the commit-msg git hook (path argument) and in CI (--range).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

TYPES = frozenset({"feat", "fix", "refactor", "perf", "test", "build", "ci", "docs", "chore"})
SCOPES = frozenset(
    {"sweep", "mpi", "jobs", "cluster", "image", "infra", "tools", "metrics", "hooks", "ci", "docs"}
)
SUBJECT_LIMIT = 60
BODY_WIDTH = 72
NON_IMPERATIVE = re.compile(r"^(add|fix|updat|remov|chang|mov)(ed|es|ing|s)$")
PLACEHOLDERS = frozenset({"wip", "update", "misc", "fixes", "changes", "cleanup", "stuff"})
HEADER = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z]+)\))?: (?P<subject>\S.*)$")
TRAILER = re.compile(r"^([A-Za-z]+-[A-Za-z-]+|Fixes|Closes|Refs|Resolves): \S")


def check(message: str) -> list[str]:
    """Judge one commit message.

    Comment lines, as left by the commit template, are ignored.

    Args:
        message: The full message, first line and optional body.

    Returns:
        One plain-words problem per rule broken; empty when the message is fine.
    """
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ["message is empty"]
    problems = _check_header(lines[0])
    if len(lines) > 1:
        problems += _check_body(lines[1:])
    return problems


def _check_header(header: str) -> list[str]:
    if len(header) > SUBJECT_LIMIT:
        return [f"first line is {len(header)} characters; the limit is {SUBJECT_LIMIT}"]
    match = HEADER.match(header)
    if match is None:
        return ["first line is not '<type>(<scope>): <subject>'"]
    problems = []
    if match["type"] not in TYPES:
        problems.append(f"type '{match['type']}' is not one of {_sorted(TYPES)}")
    if match["scope"] is not None and match["scope"] not in SCOPES:
        problems.append(f"scope '{match['scope']}' is not one of {_sorted(SCOPES)}")
    return problems + _check_subject(match["subject"])


def _check_subject(subject: str) -> list[str]:
    problems = []
    first_word = subject.split(maxsplit=1)[0]
    if subject[0] != subject[0].lower():
        problems.append("subject starts with a capital; use lowercase")
    if subject.endswith("."):
        problems.append("subject ends with a full stop; drop it")
    if NON_IMPERATIVE.match(first_word):
        problems.append(f"subject starts with '{first_word}'; use the imperative")
    if subject in PLACEHOLDERS:
        problems.append(f"subject '{subject}' says nothing; say what changed")
    return problems


def _check_body(rest: Sequence[str]) -> list[str]:
    if rest[0].strip():
        return ["body must be separated from the first line by a blank line"]
    problems = [
        f"body line {n} is {len(line)} characters; wrap at {BODY_WIDTH}"
        for n, line in enumerate(rest, start=2)
        if len(line) > BODY_WIDTH
    ]
    last_paragraph = "\n".join(rest).strip().rsplit("\n\n", 1)[-1].splitlines()
    if last_paragraph and all(TRAILER.match(line) for line in last_paragraph):
        problems.append("message ends with a trailer block; trailers are not used here")
    return problems


def messages_in_range(revision_range: str, repo: Path) -> list[str]:
    """Full messages of the commits in a git revision range, newest first."""
    output = subprocess.run(
        ["git", "log", "--format=%B%x00", revision_range],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [m.strip() for m in output.split("\0") if m.strip()]


def _sorted(values: frozenset[str]) -> str:
    return ", ".join(sorted(values))


def _report(label: str, problems: Sequence[str]) -> None:
    print(label)
    for problem in problems:
        print(f"  {problem}")


def main(argv: Sequence[str] | None = None) -> int:
    """Check a message file, a revision range, or standard input.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 when every message passes, 1 otherwise, with problems on stdout.
    """
    parser = argparse.ArgumentParser(description="check commit messages against the house format")
    parser.add_argument("path", nargs="?", help="file holding one commit message")
    parser.add_argument("--range", dest="revision_range", help="git revision range to check")
    parser.add_argument("--repo", type=Path, default=Path(), help="repository to read from")
    args = parser.parse_args(argv)
    if args.revision_range:
        messages = messages_in_range(args.revision_range, args.repo)
    elif args.path:
        messages = [Path(args.path).read_text()]
    else:
        messages = [sys.stdin.read()]
    failed = False
    for message in messages:
        problems = check(message)
        if problems:
            failed = True
            _report(message.splitlines()[0] if message.strip() else "<empty>", problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
