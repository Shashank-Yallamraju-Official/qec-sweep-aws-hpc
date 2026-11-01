"""Loop time and cost per sweep, before and after stage 15, side by side in one figure.

Each side is one run: its loop is timed as ``loop_report`` does and its cost
priced as ``cost_report`` does, so the plot adds nothing the records and GitHub
do not already say.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl

from results.run import RECORD, read_cells, read_record
from results.store import locate
from tools.cost_report import (
    billed_node_hours,
    cost,
    on_demand_price,
    parse_run,
    running_node_hours,
)
from tools.loop_report import REPOSITORY, Fetch, Loop, gh_api, time_loop

mpl.use("Agg")
import matplotlib.pyplot as plt  # the backend must be chosen before this import

Price = Callable[[str], float]
"""An instance type to its hourly on-demand rate."""

# The wait between the image and a submission is a person's, not the platform's, and
# runs to a day in the records; it is written beside each bar rather than stacked on it.
PHASES = (
    ("build", "commit to image built", "#4c72b0"),
    ("cluster", "submission to first cell", "#dd8452"),
)


@dataclass(frozen=True)
class Measured:
    """One run's place on the figure: how long its loop took and what it cost.

    Attributes:
        label: ``before`` or ``after``.
        loop: The loop the run closed.
        running: Dollars while cells ran, on demand.
        billed: Dollars once the idle tail is billed, on demand.
    """

    label: str
    loop: Loop
    running: float
    billed: float


def measure(label: str, address: str, fetch: Fetch, price: Price, repository: str) -> Measured:
    """Time and price the run at an address."""
    store, key = locate(address)
    record = read_record(store, key)
    loop = time_loop(record, read_cells(store, key), fetch, repository)
    run = parse_run(json.loads(store.read(f"{key}/{RECORD}")))
    rate = price(run.instance_type)
    return Measured(
        label=label,
        loop=loop,
        running=cost(running_node_hours(run), rate),
        billed=cost(billed_node_hours(run), rate),
    )


def minutes(loop: Loop, phase: str) -> float:
    """One phase of a loop, in minutes."""
    span = getattr(loop, phase)
    return float(span.total_seconds() / 60)


def plot(before: Measured, after: Measured, out: Path) -> None:
    """Two panels: the loop's phases stacked, and the cost running against billed."""
    sides = (before, after)
    labels = [m.label for m in sides]
    fig, (loop_ax, cost_ax) = plt.subplots(1, 2, figsize=(9, 4))
    bottom = [0.0, 0.0]
    for phase, name, colour in PHASES:
        heights = [minutes(m.loop, phase) for m in sides]
        loop_ax.bar(labels, heights, bottom=bottom, label=name, color=colour, width=0.6)
        bottom = [b + h for b, h in zip(bottom, heights, strict=True)]
    for label, top, m in zip(labels, bottom, sides, strict=True):
        note = f"waited {minutes(m.loop, 'wait'):.0f} min"
        loop_ax.annotate(note, (label, top), ha="center", va="bottom", fontsize="small")
    loop_ax.set_ylim(top=max(bottom) * 1.15)
    loop_ax.set_ylabel("minutes the platform took, commit to first cell")
    loop_ax.set_title("loop time")
    loop_ax.legend(fontsize="small")
    running = [m.running for m in sides]
    tail = [m.billed - m.running for m in sides]
    cost_ax.bar(labels, running, label="while cells ran", color="#55a868", width=0.6)
    cost_ax.bar(labels, tail, bottom=running, label="idle tail", color="#c44e52", width=0.6)
    cost_ax.set_ylabel("dollars per sweep, on demand")
    cost_ax.set_title("cost per sweep")
    cost_ax.legend(fontsize="small")
    for ax in (loop_ax, cost_ax):
        ax.grid(visible=True, axis="y", alpha=0.3)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def summary(before: Measured, after: Measured) -> str:
    """The two ratios the stage is judged on, with the waits beside them, in one line."""
    loop_before, loop_after = minutes(before.loop, "platform"), minutes(after.loop, "platform")
    waits = f"{minutes(before.loop, 'wait'):.1f} min -> {minutes(after.loop, 'wait'):.1f} min"
    return (
        f"loop {loop_before:.1f} min -> {loop_after:.1f} min ({loop_after / loop_before:.2f}x) "
        f"with {waits} of waiting, "
        f"billed ${before.billed:.3f} -> ${after.billed:.3f} ({after.billed / before.billed:.2f}x)"
    )


def main(
    argv: Sequence[str] | None = None, fetch: Fetch = gh_api, price: Price = on_demand_price
) -> int:
    """Draw the before-and-after figure for two runs and print the ratios.

    Args:
        argv: ``--before <run> --after <run> [--out png] [--repository owner/name]``.
        fetch: How GitHub is read; the default goes through ``gh``.
        price: Where hourly rates come from; the default is the pricing API.

    Returns:
        Exit status: 0 on success, 2 when a run cannot be timed or priced.
    """
    parser = argparse.ArgumentParser(
        prog="loop-plot", description="loop time and cost per sweep, before and after"
    )
    parser.add_argument("--before", required=True, help="the baseline run's address")
    parser.add_argument("--after", required=True, help="the run after the changes")
    parser.add_argument("--out", type=Path, default=Path("plots/loop.png"), help="PNG to write")
    parser.add_argument(
        "--repository", default=REPOSITORY, help="the GitHub repository, owner/name"
    )
    args = parser.parse_args(argv)
    try:
        before = measure("before", args.before, fetch, price, args.repository)
        after = measure("after", args.after, fetch, price, args.repository)
    except (FileNotFoundError, ValueError) as error:
        print(f"loop-plot: {error}", file=sys.stderr)
        return 2
    plot(before, after, args.out)
    print(f"{summary(before, after)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
