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

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client

PROJECT = "qec-sweep"
CLUSTER_TAG = "parallelcluster:cluster-name"


@dataclass(frozen=True)
class Instance:
    id: str
    type: str
    launched: datetime
    cluster: str | None


def instance_from(raw: Mapping[str, Any]) -> Instance:
    tags = {tag["Key"]: tag["Value"] for tag in raw.get("Tags", [])}
    return Instance(
        id=raw["InstanceId"],
        type=raw["InstanceType"],
        launched=raw["LaunchTime"],
        cluster=tags.get(CLUSTER_TAG),
    )


def stale(instances: Sequence[Instance], now: datetime, max_age: timedelta) -> list[Instance]:
    return [i for i in instances if i.cluster is None and now - i.launched > max_age]


def summary(running: Sequence[Instance], reaped: Sequence[Instance], now: datetime) -> str:
    lines = [f"{i.id} {i.type} up {_uptime(now - i.launched)}" for i in running]
    terminated = ", ".join(i.id for i in reaped) or "none"
    return "\n".join([*lines, f"terminated: {terminated}"]) + "\n"


def running_instances(ec2: EC2Client) -> list[Instance]:
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[
            {"Name": "tag:project", "Values": [PROJECT]},
            {"Name": "instance-state-name", "Values": ["pending", "running"]},
        ]
    )
    return [
        instance_from(raw)
        for page in pages
        for reservation in page["Reservations"]
        for raw in reservation["Instances"]
    ]


def handler(_event: object, _context: object) -> dict[str, int]:
    ec2 = boto3.client("ec2")
    now = datetime.now(UTC)
    running = running_instances(ec2)
    reaped = stale(running, now, timedelta(hours=float(os.environ.get("MAX_HOURS", "4"))))
    if reaped:
        ec2.terminate_instances(InstanceIds=[i.id for i in reaped])
    if running:
        boto3.client("sns").publish(
            TopicArn=os.environ["TOPIC_ARN"],
            Subject=f"{PROJECT}: {len(running)} instance(s) running",
            Message=summary(running, reaped, now),
        )
    return {"running": len(running), "reaped": len(reaped)}


def _uptime(age: timedelta) -> str:
    minutes = int(age.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60}m"
