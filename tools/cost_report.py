"""Cost per sweep from a run's own record, priced at the published rates.

This account cannot activate cost-allocation tags, so a run is costed from
what it recorded: node count, instance type and timing. Two figures come out:
the node-hours while the run was going, and the node-hours EC2 bills once the
idle tail before scale-down is added, which back-to-back runs share.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, cast

import boto3

if TYPE_CHECKING:
    from mypy_boto3_ec2.literals import InstanceTypeType

IDLE = timedelta(minutes=10)
REGION = "us-east-2"
ZONE = "us-east-2b"
LOCATION = "US East (Ohio)"


@dataclass(frozen=True)
class Run:
    """What a sweep used, as ``jobs/sweep.sh`` and ``jobs/sync.sbatch`` recorded it."""

    run: str
    queue: str
    instance_type: str
    nodes: int
    submitted: datetime
    finished: datetime


def read_run(path: Path) -> Run:
    """Read a ``run.json``; the nodes the run actually used beat the count it asked for.

    Raises:
        ValueError: When the record names no node count at all.
    """
    record = json.loads(path.read_text())
    nodes = record.get("nodes_used") or record.get("nodes")
    if not nodes:
        msg = f"{path} has no node count: neither nodes_used nor nodes"
        raise ValueError(msg)
    return Run(
        run=record["run"],
        queue=record["queue"],
        instance_type=record["instance_type"],
        nodes=int(nodes),
        submitted=datetime.fromisoformat(record["submitted"]),
        finished=datetime.fromisoformat(record["finished"]),
    )


def running_node_hours(run: Run) -> float:
    """Node-hours between submission and the last cell written."""
    return run.nodes * (run.finished - run.submitted).total_seconds() / 3600


def billed_node_hours(run: Run, idle: timedelta = IDLE) -> float:
    """Node-hours EC2 bills if nothing follows: the run plus the idle tail before scale-down."""
    return run.nodes * (run.finished - run.submitted + idle).total_seconds() / 3600


def cost(node_hours: float, price_per_hour: float) -> float:
    """Dollars for node-hours at one hourly rate."""
    return node_hours * price_per_hour


def only[T](items: Sequence[T], what: str) -> T:
    """The single answer an AWS lookup should give, or a message saying how to supply it."""
    if not items:
        msg = f"no {what}; pass it on the command line"
        raise ValueError(msg)
    return items[0]


def on_demand_price(instance_type: str) -> float:
    """Published Linux on-demand rate for the type in this region, from the pricing API."""
    pricing = boto3.client("pricing", region_name="us-east-1")
    fields = {
        "instanceType": instance_type,
        "location": LOCATION,
        "operatingSystem": "Linux",
        "tenancy": "Shared",
        "preInstalledSw": "NA",
        "capacitystatus": "Used",
    }
    page = pricing.get_products(
        ServiceCode="AmazonEC2",
        Filters=[{"Type": "TERM_MATCH", "Field": f, "Value": v} for f, v in fields.items()],
        MaxResults=1,
    )
    product = json.loads(only(page["PriceList"], f"on-demand price for {instance_type}"))
    term = next(iter(product["terms"]["OnDemand"].values()))
    dimension = next(iter(term["priceDimensions"].values()))
    return float(dimension["pricePerUnit"]["USD"])


def spot_price(instance_type: str, at: datetime) -> float:
    """Spot rate for the type in the cluster's zone at a moment."""
    ec2 = boto3.client("ec2", region_name=REGION)
    history = ec2.describe_spot_price_history(
        InstanceTypes=[cast("InstanceTypeType", instance_type)],
        ProductDescriptions=["Linux/UNIX"],
        AvailabilityZone=ZONE,
        StartTime=at,
        EndTime=at,
    )
    entry = only(history["SpotPriceHistory"], f"spot price for {instance_type} at {at:%FT%TZ}")
    return float(entry["SpotPrice"])


def report(run: Run, on_demand: float, spot: float) -> str:
    """Three lines: what ran, then its cost on demand and on spot, running and billed."""
    minutes = (run.finished - run.submitted).total_seconds() / 60
    running, billed = running_node_hours(run), billed_node_hours(run)

    def priced(label: str, rate: float) -> str:
        dollars = f"${cost(running, rate):.3f} running, ${cost(billed, rate):.3f} billed"
        return f"  {label}: {dollars} at ${rate:.4f}/h"

    what = f"{run.run} on {run.queue}: {run.nodes} x {run.instance_type} for {minutes:.1f} min"
    return "\n".join(
        [
            f"{what}: {running:.2f} node-hours running, {billed:.2f} billed",
            priced("on demand", on_demand),
            priced("spot", spot),
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Cost one run; rates come from AWS unless given, and a given rate of zero is honoured."""
    parser = argparse.ArgumentParser(prog="cost-report", description="cost per sweep from run.json")
    parser.add_argument("run", type=Path, help="a run.json written by jobs/sync.sbatch")
    parser.add_argument("--on-demand", type=float, help="hourly rate, else fetched")
    parser.add_argument("--spot", type=float, help="hourly rate, else fetched")
    args = parser.parse_args(argv)
    run = read_run(args.run)
    on_demand = on_demand_price(run.instance_type) if args.on_demand is None else args.on_demand
    when = run.submitted.astimezone(UTC)
    spot = spot_price(run.instance_type, when) if args.spot is None else args.spot
    print(report(run, on_demand, spot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
