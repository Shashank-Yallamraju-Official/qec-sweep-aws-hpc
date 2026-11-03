"""Both decoders' logical error rates by distance, in one figure: the ``decoder-plot`` command.

Two evaluations of the same cells, one by matching and one by the learned decoder,
are joined cell by cell as ``results-compare`` joins them, so the figure draws
nothing the comparison does not say: each distance keeps one colour, the decoder
is told by the line, and the error bars are the Wilson intervals the cells carry.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl

from results.compare import CellComparison, Comparison, compare
from results.run import read_cells
from results.store import locate

mpl.use("Agg")
import matplotlib.pyplot as plt  # the backend must be chosen before this import

# One hue per distance in a fixed order, adjacent pairs apart under colour-blindness
# (checked); the decoder is carried by line style and marker, never by colour alone.
DISTANCE_COLOURS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")
MATCHING = ("matching", "-", "o")
LEARNED = ("learned", "--", "s")


def by_distance(comparison: Comparison) -> dict[int, list[CellComparison]]:
    """The shared cells grouped by distance, each group by rising noise rate."""
    groups: dict[int, list[CellComparison]] = {}
    for cell in comparison.cells:
        groups.setdefault(cell.cell.distance, []).append(cell)
    return {d: sorted(cells, key=lambda c: c.cell.noise) for d, cells in sorted(groups.items())}


def plot(comparison: Comparison, noise_model: str, out: Path) -> tuple[int, int]:
    """Logical error rate against noise rate, log-log, both decoders per distance.

    Cells where a decoder saw no error have no point on a log axis and are left out.

    Returns:
        How many distances and how many noise rates were drawn.

    Raises:
        ValueError: When there are more distances than the fixed hues can tell apart.
    """
    groups = by_distance(comparison)
    if len(groups) > len(DISTANCE_COLOURS):
        msg = f"{len(groups)} distances, but only {len(DISTANCE_COLOURS)} hues keep apart"
        raise ValueError(msg)
    fig, ax = plt.subplots(figsize=(7, 5))
    for colour, (distance, cells) in zip(
        DISTANCE_COLOURS[: len(groups)], groups.items(), strict=True
    ):
        for side, (name, style, marker) in (("a", MATCHING), ("b", LEARNED)):
            drawn = [c for c in cells if getattr(c, side).errors > 0]
            rates = [getattr(c, side).rate for c in drawn]
            below = [getattr(c, side).rate - getattr(c, side).low for c in drawn]
            above = [getattr(c, side).high - getattr(c, side).rate for c in drawn]
            ax.errorbar(
                [c.cell.noise for c in drawn],
                rates,
                yerr=[below, above],
                color=colour,
                linestyle=style,
                marker=marker,
                markersize=4,
                linewidth=1.5,
                capsize=2,
                label=f"d = {distance}, {name}",
            )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("physical error rate p")
    ax.set_ylabel("logical error rate per shot")
    shots = comparison.cells[0].cell.shots
    ax.set_title(f"Learned decoder against matching, {noise_model} noise, {shots:,} shots per cell")
    ax.grid(visible=True, which="both", alpha=0.3)
    ax.legend(fontsize="small")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return len(groups), len({c.cell.noise for c in comparison.cells})


def summary(comparison: Comparison) -> str:
    """One line per distance: learned over matching at each noise rate, and the verdicts."""
    lines = []
    for distance, cells in by_distance(comparison).items():
        ratios = ", ".join(
            f"{'n/a' if c.ratio is None else f'{c.ratio:.2f}'} at p={c.cell.noise}" for c in cells
        )
        verdicts = {c.verdict for c in cells}
        counts = "; ".join(
            f"{sum(1 for c in cells if c.verdict == v)} {v}"
            for v in ("lower", "within", "higher")
            if v in verdicts
        )
        lines.append(f"d={distance}: learned/matching {ratios}; {counts}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Draw two evaluations against each other and print the ratios.

    Args:
        argv: ``<matching run> <learned run> [--out png]``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when a run has no cells, the runs share none, or
        there are more distances than the figure can tell apart.
    """
    parser = argparse.ArgumentParser(
        prog="decoder-plot", description="both decoders' error rates by distance"
    )
    parser.add_argument(
        "matching", help="the evaluation by matching, an s3:// address or directory"
    )
    parser.add_argument("learned", help="the evaluation by the learned decoder")
    parser.add_argument(
        "--out", type=Path, default=Path("plots/decoders.png"), help="PNG file to write"
    )
    args = parser.parse_args(argv)
    try:
        (store_a, key_a), (store_b, key_b) = locate(args.matching), locate(args.learned)
        cells_a, cells_b = read_cells(store_a, key_a), read_cells(store_b, key_b)
    except FileNotFoundError as error:
        print(f"decoder-plot: {error}", file=sys.stderr)
        return 2
    comparison = compare(cells_a, cells_b)
    if not comparison.cells:
        print("decoder-plot: the runs share no cell", file=sys.stderr)
        return 2
    noise_model = str(cells_a.to_pylist()[0].get("noise_model", "depolarising"))
    try:
        distances, rates = plot(comparison, noise_model, args.out)
    except ValueError as error:
        print(f"decoder-plot: {error}", file=sys.stderr)
        return 2
    print(f"{summary(comparison)}\n{distances} distances, {rates} noise rates -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
