"""Strong scaling from a run's records: the ``statevector-plot`` command."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib as mpl

mpl.use("Agg")
import matplotlib.pyplot as plt  # the backend must be chosen before this import

COMPUTE, EXCHANGE = "#2a78d6", "#eb6834"


def records(directory: Path) -> list[dict[str, Any]]:
    """The ``nodes<N>.json`` records of one run, in order of node count."""
    found = [json.loads(path.read_text()) for path in directory.glob("nodes*.json")]
    return sorted(found, key=lambda record: int(record["ranks"]))


def efficiency(runs: Sequence[dict[str, Any]]) -> list[float]:
    """Strong-scaling efficiency against the smallest run: T(1) / (N x T(N)), as per cent."""
    base = runs[0]
    return [
        100 * base["seconds"]["total"] * base["ranks"] / (run["ranks"] * run["seconds"]["total"])
        for run in runs
    ]


def plot(runs: Sequence[dict[str, Any]], out: Path) -> list[int]:
    """Draw where the time went per node count beside the efficiency it bought.

    Args:
        runs: Records as ``statevector`` writes them, smallest first.
        out: PNG path to write.

    Returns:
        The node counts drawn, as ranks over the smallest run's ranks.

    Raises:
        ValueError: If there are no records.
    """
    if not runs:
        msg = "no nodes*.json records to plot"
        raise ValueError(msg)
    nodes = [run["ranks"] // runs[0]["ranks"] for run in runs]
    labels = [str(n) for n in nodes]
    compute = [run["seconds"]["compute"] for run in runs]
    exchange = [run["seconds"]["exchange"] for run in runs]
    fig, (time_axis, efficiency_axis) = plt.subplots(1, 2, figsize=(10, 4.5))
    time_axis.bar(labels, compute, color=COMPUTE, label="computing", width=0.6)
    time_axis.bar(labels, exchange, bottom=compute, color=EXCHANGE, label="exchanging", width=0.6)
    for label, run in zip(labels, runs, strict=True):
        total = run["seconds"]["total"]
        time_axis.text(label, total, f"{total:.1f} s", ha="center", va="bottom", fontsize=9)
    time_axis.set_xlabel("nodes")
    time_axis.set_ylabel("seconds on the slowest rank")
    time_axis.set_title("where the time goes")
    time_axis.legend(frameon=False)
    efficiency_axis.plot(labels, efficiency(runs), marker="o", color=COMPUTE, linewidth=2)
    efficiency_axis.axhline(100, color="#999999", linestyle="--", linewidth=1)
    efficiency_axis.set_ylim(0, 110)
    efficiency_axis.set_xlabel("nodes")
    efficiency_axis.set_ylabel("strong-scaling efficiency, %")
    efficiency_axis.set_title("T(1) / (N x T(N))")
    first = runs[0]
    fig.suptitle(
        f"{first['qubits']} qubits, {first['layers']} layers, "
        f"{first['ranks']} ranks per node, {first['kernel']} kernel"
    )
    for axis in (time_axis, efficiency_axis):
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(visible=True, axis="y", alpha=0.3)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return nodes


def main(argv: Sequence[str] | None = None) -> int:
    """Plot a run's records to a PNG and print what was drawn.

    Args:
        argv: ``<run directory> <png file>``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when the directory holds no records.
    """
    parser = argparse.ArgumentParser(prog="statevector-plot", description="draw strong scaling")
    parser.add_argument("run", type=Path, help="directory of nodes<N>.json records")
    parser.add_argument("out", type=Path, help="PNG file to write")
    args = parser.parse_args(argv)
    try:
        nodes = plot(records(args.run), args.out)
    except ValueError as error:
        print(f"statevector-plot: {error}", file=sys.stderr)
        return 2
    print(f"{len(nodes)} node counts, {nodes[0]} to {nodes[-1]} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
