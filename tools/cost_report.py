"""Cost per sweep from a run's own record, priced at the published rates.

This account cannot activate cost-allocation tags, so a run is costed from
what it recorded: node count, instance type and timing, plus the idle tail
before the scheduler scales the nodes away.
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
    """What a sweep used, as ``jobs/sweep.sh`` and ``jobs/sync.sbatch`` recorded it.

    Attributes:
        run: The run's timestamp name.
        queue: Slurm partition it ran on.
        instance_type: EC2 instance type of that queue.
        nodes: Nodes that took part.
        submitted: When the array was submitted.
        finished: When the array finished.
    """

    run: str
    queue: str
    instance_type: str
    nodes: int
    submitted: datetime
    finished: datetime


def read_run(path: Path) -> Run:
    """Read a ``run.json``; the nodes the queue had up at the end beat the requested count."""
    record = json.loads(path.read_text())
    return Run(
        run=record["run"],
        queue=record["queue"],
        instance_type=record["instance_type"],
        nodes=int(record.get("nodes_up") or record["nodes"]),
        submitted=datetime.fromisoformat(record["submitted"]),
        finished=datetime.fromisoformat(record["finished"]),
    )


def billed_node_hours(run: Run, idle: timedelta = IDLE) -> float:
    """Node-hours EC2 bills for: every node from submission until the idle tail scales it away."""
    return run.nodes * (run.finished - run.submitted + idle).total_seconds() / 3600


def cost(run: Run, price_per_hour: float) -> float:
    """Dollars for the run at one hourly rate."""
    return billed_node_hours(run) * price_per_hour


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
    product = json.loads(page["PriceList"][0])
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
    return float(history["SpotPriceHistory"][0]["SpotPrice"])


def report(run: Run, on_demand: float, spot: float) -> str:
    """Three lines: what ran, and what it costs on demand and on spot."""
    minutes = (run.finished - run.submitted).total_seconds() / 60
    what = f"{run.run} on {run.queue}: {run.nodes} x {run.instance_type} for {minutes:.1f} min"
    return "\n".join(
        [
            f"{what}, billed {billed_node_hours(run):.2f} node-hours",
            f"  on demand: ${cost(run, on_demand):.3f} at ${on_demand:.4f}/h",
            f"  spot: ${cost(run, spot):.3f} at ${spot:.4f}/h",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Cost one run; rates come from AWS unless given.

    Args:
        argv: ``<run.json> [--on-demand RATE] [--spot RATE]``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status 0.
    """
    parser = argparse.ArgumentParser(prog="cost-report", description="cost per sweep from run.json")
    parser.add_argument("run", type=Path, help="a run.json written by jobs/sync.sbatch")
    parser.add_argument("--on-demand", type=float, help="hourly rate, else fetched")
    parser.add_argument("--spot", type=float, help="hourly rate, else fetched")
    args = parser.parse_args(argv)
    run = read_run(args.run)
    on_demand = args.on_demand or on_demand_price(run.instance_type)
    spot = args.spot or spot_price(run.instance_type, run.submitted.astimezone(UTC))
    print(report(run, on_demand, spot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
