"""The loop, timed from a commit to the first cell its sweep wrote on the cluster.

Everything it needs was recorded as the loop ran: the commit is the image's
tag, GitHub holds when it was committed and when the image workflow built it,
the run's record holds when the sweep was submitted and its cells hold when
each started. The report splits the loop where the time can go: CI, the wait
for someone to submit, and the cluster from submission to the first cell.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from results.run import RunRecord, read_cells, read_record
from results.store import locate

REPOSITORY = "Shashank-Yallamraju-Official/qec-sweep-aws-hpc"
IMAGE_WORKFLOW = "image"
TAG = re.compile(r"^(?P<uri>.*/(?P<name>[^/:]+)):(?P<tag>[^:]+)$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")

Fetch = Callable[[str], Any]
"""A GitHub API path or URL to the JSON it returns."""


@dataclass(frozen=True)
class ImageRef:
    """An image as a run names it: which image, built from which commit."""

    name: str
    commit: str


@dataclass(frozen=True)
class Loop:
    """One pass round the loop, from a commit to the first cell its image decoded.

    Attributes:
        run: The run that closed the loop.
        commit: The commit the image was built from.
        committed: When the commit was made.
        image_built: When CI finished building the image.
        submitted: When the sweep was submitted.
        first_cell: When the first cell started decoding.
    """

    run: str
    commit: str
    committed: datetime
    image_built: datetime
    submitted: datetime
    first_cell: datetime

    @property
    def build(self) -> timedelta:
        """Commit to image built: CI's queue and the build."""
        return self.image_built - self.committed

    @property
    def wait(self) -> timedelta:
        """Image built to submission: the time nobody was running the loop."""
        return self.submitted - self.image_built

    @property
    def cluster(self) -> timedelta:
        """Submission to first cell: nodes booting and the image being pulled."""
        return self.first_cell - self.submitted

    @property
    def total(self) -> timedelta:
        """Commit to first cell."""
        return self.first_cell - self.committed

    @property
    def platform(self) -> timedelta:
        """The loop without the wait: what the platform took, build and cluster together."""
        return self.build + self.cluster


def parse_image(uri: str) -> ImageRef:
    """The image name and commit an image URI carries in its tag.

    Raises:
        ValueError: When the tag is not a commit, such as ``latest``.
    """
    match = TAG.match(uri)
    if not match or not COMMIT.match(match["tag"]):
        tag = match["tag"] if match else uri
        msg = f"{tag} is not a commit; the loop is timed from the commit an image was built from"
        raise ValueError(msg)
    return ImageRef(name=match["name"], commit=match["tag"])


def committed_at(fetch: Fetch, repository: str, commit: str) -> datetime:
    """When the commit was made, as GitHub records it."""
    response = fetch(f"repos/{repository}/commits/{commit}")
    return _when(response["commit"]["committer"]["date"])


def image_built_at(fetch: Fetch, repository: str, image: ImageRef) -> datetime:
    """When the image workflow finished building this image for its commit.

    Raises:
        ValueError: When no image workflow ran for the commit, or built no such image.
    """
    runs = fetch(f"repos/{repository}/actions/runs?head_sha={image.commit}&per_page=100")
    for run in runs["workflow_runs"]:
        if run["name"] != IMAGE_WORKFLOW:
            continue
        for job in fetch(run["jobs_url"])["jobs"]:
            if (
                job["name"] == f"{IMAGE_WORKFLOW} ({image.name})"
                and job.get("conclusion") == "success"
            ):
                return _when(job["completed_at"])
    msg = f"no image workflow run built {image.commit[:7]} into {image.name}"
    raise ValueError(msg)


def first_cell(cells: pa.Table) -> datetime:
    """When the earliest cell started decoding."""
    started = pc.min(cells["started"]).as_py()
    if not isinstance(started, datetime):
        msg = "the cells carry no start time"
        raise TypeError(msg)
    return started


def time_loop(record: RunRecord, cells: pa.Table, fetch: Fetch, repository: str) -> Loop:
    """Time the loop a run closed, from what it recorded and what GitHub holds.

    Raises:
        ValueError: When the record names no image.
    """
    if record.image is None:
        msg = f"{record.key} names no image"
        raise ValueError(msg)
    image = parse_image(record.image)
    return Loop(
        run=record.run,
        commit=image.commit,
        committed=committed_at(fetch, repository, image.commit),
        image_built=image_built_at(fetch, repository, image),
        submitted=record.submitted,
        first_cell=first_cell(cells),
    )


def report(loop: Loop) -> str:
    """The loop's total and its three phases, in minutes."""

    def minutes(span: timedelta) -> str:
        return f"{span.total_seconds() / 60:.1f} min"

    return "\n".join(
        [
            f"{loop.run}: commit {loop.commit[:7]} to its first cell in {minutes(loop.total)}",
            f"  commit to image built: {minutes(loop.build)}",
            f"  image built to submission: {minutes(loop.wait)}",
            f"  submission to first cell: {minutes(loop.cluster)}",
        ]
    )


def gh_api(path: str) -> Any:  # noqa: ANN401
    """The JSON GitHub returns for a path, through the ``gh`` command's login."""
    out = subprocess.run(["gh", "api", path], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def main(argv: Sequence[str] | None = None, fetch: Fetch = gh_api) -> int:
    """Time the loop one run closed and print the report.

    Args:
        argv: ``<run> [--repository owner/name]``; ``None`` reads ``sys.argv``.
        fetch: How GitHub is read; the default goes through ``gh``.

    Returns:
        Exit status: 0 on success, 2 when the run has no cells or no image commit.
    """
    parser = argparse.ArgumentParser(
        prog="loop-report", description="time the loop from a commit to its first cell"
    )
    parser.add_argument(
        "run", help="the run that closed the loop, s3://bucket/sweeps/<run> or a directory"
    )
    parser.add_argument(
        "--repository", default=REPOSITORY, help="the GitHub repository, owner/name"
    )
    args = parser.parse_args(argv)
    store, key = locate(args.run)
    try:
        loop = time_loop(read_record(store, key), read_cells(store, key), fetch, args.repository)
    except (FileNotFoundError, ValueError) as error:
        print(f"loop-report: {error}", file=sys.stderr)
        return 2
    print(report(loop))
    return 0


def _when(text: str) -> datetime:
    return datetime.fromisoformat(text)


if __name__ == "__main__":
    sys.exit(main())
