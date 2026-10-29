"""Hourly check that nothing is left running.

Emails while any project instance runs and terminates instances past the
age limit, except members of a ParallelCluster, which has its own lifecycle.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client

PROJECT = "qec-sweep"
CLUSTER_TAG = "parallelcluster:cluster-name"


@dataclass(frozen=True)
class Instance:
    """The little the reaper needs to know about a running instance.

    Attributes:
        id: EC2 instance id.
        type: Instance type, for the email.
        launched: Launch time, from which age is measured.
        cluster: ParallelCluster name when the instance belongs to one, else ``None``.
    """

    id: str
    type: str
    launched: datetime
    cluster: str | None


def instance_from(raw: Mapping[str, Any]) -> Instance:
    """Pick the fields the reaper uses out of a DescribeInstances record."""
    tags = {tag["Key"]: tag["Value"] for tag in raw.get("Tags", [])}
    return Instance(
        id=raw["InstanceId"],
        type=raw["InstanceType"],
        launched=raw["LaunchTime"],
        cluster=tags.get(CLUSTER_TAG),
    )


def stale(instances: Sequence[Instance], now: datetime, max_age: timedelta) -> list[Instance]:
    """Instances past ``max_age`` that no cluster is responsible for."""
    return [i for i in instances if i.cluster is None and now - i.launched > max_age]


def summary(
    running: Sequence[Instance],
    reaped: Sequence[Instance],
    now: datetime,
    failure: str | None = None,
) -> str:
    """The email body: one line per running instance, then what happened to the stale ones.

    Args:
        running: Every instance seen this hour.
        reaped: The subset that was due for termination.
        now: When the check ran, for uptimes.
        failure: The error text when terminating failed, so the email still says so.

    Returns:
        Plain text ending in either ``terminated: ...`` or ``terminate failed (...): ...``.
    """
    lines = [f"{i.id} {i.type} up {_uptime(now - i.launched)}" for i in running]
    ids = ", ".join(i.id for i in reaped)
    outcome = f"terminate failed ({ids}): {failure}" if failure else f"terminated: {ids or 'none'}"
    return "\n".join([*lines, outcome]) + "\n"


def running_instances(ec2: EC2Client) -> list[Instance]:
    """Every pending or running instance in the region.

    The account runs nothing but this project, so all of them count, tagged or not.
    """
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["pending", "running"]}]
    )
    return [
        instance_from(raw)
        for page in pages
        for reservation in page["Reservations"]
        for raw in reservation["Instances"]
    ]


def handler(_event: object, _context: object) -> dict[str, int]:
    """Lambda entry point, run hourly by EventBridge.

    Reads ``TOPIC_ARN`` and ``MAX_HOURS`` from the environment. Emails only
    while something is running, so a quiet account produces no mail.

    Returns:
        How many instances were running and how many were stale enough to terminate;
        whether the terminate succeeded is in the email, not here.
    """
    ec2 = boto3.client("ec2")
    now = datetime.now(UTC)
    running = running_instances(ec2)
    reaped = stale(running, now, timedelta(hours=float(os.environ.get("MAX_HOURS", "4"))))
    failure = _terminate(ec2, reaped) if reaped else None
    if running:
        boto3.client("sns").publish(
            TopicArn=os.environ["TOPIC_ARN"],
            Subject=f"{PROJECT}: {len(running)} instance(s) running",
            Message=summary(running, reaped, now, failure),
        )
    return {"running": len(running), "reaped": len(reaped)}


def _terminate(ec2: EC2Client, instances: Sequence[Instance]) -> str | None:
    """Returns the failure to put in the email; the email must go out either way."""
    try:
        ec2.terminate_instances(InstanceIds=[i.id for i in instances])
    except ClientError as error:
        return str(error)
    return None


def _uptime(age: timedelta) -> str:
    minutes = int(age.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60}m"
