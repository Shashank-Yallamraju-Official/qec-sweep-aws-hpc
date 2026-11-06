"""The README's learning curve, drawn from the chains.

Each chain passed is read as ``decoder-diagnose`` reads it, and each evaluated cell
becomes one point: the learned decoder's logical error rate over matching's, at the
shots the chain trained on, with a bar from the outer ends of the two Wilson intervals.
The chains of the first seed are joined into one line per noise rate; a later seed
draws as hollow markers on the same hue, nudged right so both show. Matching is the
line at one. One noise model per figure, drawn as SVG in a light and a dark theme so
GitHub shows the reader the right one, and every address read is listed in the file's
description so the figure walks back to its runs.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from decoder.diagnose import diagnose
from results.store import locate
from sweep.noise import Noise
from tools.loop_figure import FONT, PALETTES

SERIES = {
    "light": ("#2a78d6", "#eb6834", "#1baf7a"),
    "dark": ("#3987e5", "#d95926", "#199e70"),
}
"""One hue per noise rate, in rate order; three slots, checked apart under colour-blindness."""
WIDTH, HEIGHT = 1240, 540
LEFT, RIGHT, TOP, BOTTOM = 96, 170, 36, 76
NUDGE = 0.04
"""Share of the x axis a later seed's markers move right, so they do not hide the first's."""
TICKS = (0.25, 0.5, 1, 2, 4, 8, 16)
THOUSAND, MILLION = 1_000, 1_000_000


@dataclass(frozen=True)
class Point:
    """One evaluated cell of one chain, as the figure plots it.

    Attributes:
        shots: Training shots of the chain.
        rate: The cell's physical noise rate.
        ratio: The learned decoder's logical error rate over matching's.
        low: The ratio's lower bar, the learned interval's floor over matching's ceiling.
        high: The ratio's upper bar, the learned interval's ceiling over matching's floor.
    """

    shots: int
    rate: float
    ratio: float
    low: float
    high: float


@dataclass(frozen=True)
class Curve:
    """One chain's points, with what they were read from.

    Attributes:
        noise: The noise model the chain ran under.
        seed: The chain's seed.
        points: One per evaluated cell, by noise rate.
        read: Every address the chain's diagnosis was read from.
    """

    noise: Noise
    seed: int
    points: tuple[Point, ...]
    read: tuple[str, ...]


def read_chain(chain: str) -> Curve:
    """Read one chain into its points.

    A cell where either decoder saw no error has no interval above zero and so no place
    on a log axis; it is left out.

    Raises:
        ValueError: When the chain trained more than one model, since the figure has one
            shot count per chain.
    """
    diagnosis = diagnose(chain)
    if len(diagnosis.trainings) != 1:
        msg = f"{chain} trained {len(diagnosis.trainings)} models; the figure takes one per chain"
        raise ValueError(msg)
    store, key = locate(chain)
    seed = int(json.loads(store.read(f"{key}/run.json").decode())["seed"])
    (training,) = diagnosis.trainings
    train_store, train_key = locate(training.key)
    shots = int(json.loads(train_store.read(f"{train_key}/train.json").decode())["shots"])
    points = tuple(
        Point(
            shots=shots,
            rate=state.cell.noise,
            ratio=state.ratio,
            low=state.learned.low / state.matching.high,
            high=state.learned.high / state.matching.low,
        )
        for state in diagnosis.cells
        if state.ratio is not None and state.matching.low > 0 and state.learned.low > 0
    )
    return Curve(diagnosis.noise, seed, points, diagnosis.read)


def check(curves: Sequence[Curve]) -> None:
    """Refuse what one figure cannot carry: two noise models, or more rates than hues.

    Raises:
        ValueError: Naming the noise models or the rate count.
    """
    noises = sorted({c.noise for c in curves})
    if len(noises) != 1:
        msg = f"one noise model per figure, not {', '.join(noises)}"
        raise ValueError(msg)
    rates = _rates(curves)
    if len(rates) > len(SERIES["light"]):
        msg = f"{len(rates)} noise rates and {len(SERIES['light'])} hues"
        raise ValueError(msg)


def draw(theme: str, curves: Sequence[Curve]) -> str:
    """The figure in one theme, as SVG text."""
    check(curves)
    c = PALETTES[theme]
    seeds = sorted({curve.seed for curve in curves})
    scale = _Scale(curves)
    parts = [
        _open(),
        f"<title>{_title(curves)}</title>",
        f"<desc>{_desc(curves)}</desc>",
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{c["bg"]}"/>',
        *_axes(c, scale),
        *_baseline(c, scale),
    ]
    for hue, rate in zip(SERIES[theme], _rates(curves), strict=False):
        labelled = False
        for s, seed in enumerate(seeds):
            points = sorted(
                (p for k in curves if k.seed == seed for p in k.points if p.rate == rate),
                key=lambda p: p.shots,
            )
            parts.extend(_series(c, scale, points, hue, nudge=s * NUDGE, hollow=s > 0))
            if points and not labelled:
                after = (len(seeds) - 1) * NUDGE
                parts.append(_end_label(c, scale, points[-1], rate, after=after))
                labelled = True
    parts.extend(_key(c, seeds))
    parts.append("</svg>")
    return "\n".join(parts)


class _Scale:
    """Log axes from the data, with room at the ends."""

    def __init__(self, curves: Sequence[Curve]) -> None:
        everything = [p for k in curves for p in k.points]
        self.shots = sorted({p.shots for p in everything})
        x0, x1 = math.log10(min(self.shots)), math.log10(max(self.shots))
        self.x0, self.x1 = x0 - 0.08 * (x1 - x0) - 0.02, x1 + 0.08 * (x1 - x0) + 0.02
        y0 = math.log10(min(1.0, *(p.low for p in everything)))
        y1 = math.log10(max(1.0, *(p.high for p in everything)))
        self.y0, self.y1 = y0 - 0.06 * (y1 - y0), y1 + 0.06 * (y1 - y0)
        self.ticks = [t for t in TICKS if self.y0 <= math.log10(t) <= self.y1]

    def x(self, shots: float, nudge: float = 0.0) -> float:
        plot = WIDTH - LEFT - RIGHT
        return LEFT + plot * ((math.log10(shots) - self.x0) / (self.x1 - self.x0) + nudge)

    def y(self, ratio: float) -> float:
        plot = HEIGHT - TOP - BOTTOM
        return TOP + plot * (1 - (math.log10(ratio) - self.y0) / (self.y1 - self.y0))


def _rates(curves: Iterable[Curve]) -> list[float]:
    return sorted({p.rate for curve in curves for p in curve.points})


def _open() -> str:
    size = f'viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}"'
    return f'<svg xmlns="http://www.w3.org/2000/svg" {size} font-family="{FONT}" role="img">'


def _title(curves: Sequence[Curve]) -> str:
    noise = escape(curves[0].noise)
    return f"Learned decoder over matching against training shots, {noise} noise"


def _desc(curves: Sequence[Curve]) -> str:
    read = sorted({address for curve in curves for address in curve.read})
    return escape("Read: " + ", ".join(read))


def _axes(c: dict[str, str], scale: _Scale) -> list[str]:
    bottom = HEIGHT - BOTTOM
    parts = [_line(LEFT, bottom, WIDTH - RIGHT, bottom, stroke=c["line"], width=1)]
    for tick in scale.ticks:
        y = scale.y(tick)
        if tick != 1:
            parts.append(_line(LEFT, y, WIDTH - RIGHT, y, stroke=c["frame"], width=1))
        parts.append(_text(LEFT - 12, y + 4, f"{tick:g}", c["muted"], 12, anchor="end"))
    for shots in scale.shots:
        x = scale.x(shots)
        parts.append(_line(x, bottom, x, bottom + 6, stroke=c["line"], width=1))
        parts.append(_text(x, bottom + 24, _compact(shots), c["muted"], 12, anchor="middle"))
    mid_x = LEFT + (WIDTH - LEFT - RIGHT) / 2
    parts.append(_text(mid_x, HEIGHT - 20, "training shots", c["text"], 13, anchor="middle"))
    mid_y = TOP + (HEIGHT - TOP - BOTTOM) / 2
    label = "learned decoder's logical error rate over matching's"
    parts.append(
        f'<text x="26" y="{mid_y}" fill="{c["text"]}" font-size="13" text-anchor="middle" '
        f'transform="rotate(-90 26 {mid_y})">{label}</text>'
    )
    return parts


def _baseline(c: dict[str, str], scale: _Scale) -> list[str]:
    y = scale.y(1)
    return [
        _line(LEFT, y, WIDTH - RIGHT, y, stroke=c["arrow"], width=1),
        _text(LEFT + 8, y - 7, "matching", c["muted"], 12),
    ]


def _series(  # noqa: PLR0913
    c: dict[str, str],
    scale: _Scale,
    points: Sequence[Point],
    hue: str,
    *,
    nudge: float,
    hollow: bool,
) -> list[str]:
    parts = []
    if len(points) > 1 and not hollow:
        path = " ".join(
            f"{'M' if i == 0 else 'L'}{scale.x(p.shots, nudge):.1f},{scale.y(p.ratio):.1f}"
            for i, p in enumerate(points)
        )
        parts.append(
            f'<path d="{path}" fill="none" stroke="{hue}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/>'
        )
    for p in points:
        x = scale.x(p.shots, nudge)
        parts.append(_line(x, scale.y(p.low), x, scale.y(p.high), stroke=hue, width=1.2))
        fill, stroke = (c["bg"], hue) if hollow else (hue, c["bg"])
        parts.append(_marker(x, scale.y(p.ratio), fill, stroke))
    return parts


def _end_label(c: dict[str, str], scale: _Scale, last: Point, rate: float, *, after: float) -> str:
    x, y = scale.x(last.shots, after) + 16, scale.y(last.ratio) + 4
    return _text(x, y, f"p = {rate:g} · {last.ratio:.2f}", c["text"], 12)


def _key(c: dict[str, str], seeds: Sequence[int]) -> list[str]:
    y = TOP + 10
    x = LEFT + 16
    parts = [
        _marker(x, y, c["arrow"], c["bg"]),
        _text(x + 12, y + 4, f"seed {seeds[0]}", c["muted"], 12),
    ]
    if len(seeds) > 1:
        x += 90
        others = ", ".join(str(s) for s in seeds[1:])
        parts.append(_marker(x, y, c["bg"], c["arrow"]))
        parts.append(_text(x + 12, y + 4, f"seed {others}, nudged right", c["muted"], 12))
    return parts


def _marker(x: float, y: float, fill: str, stroke: str) -> str:
    place = f'cx="{x:.1f}" cy="{y:.1f}" r="4.5"'
    return f'<circle {place} fill="{fill}" stroke="{stroke}" stroke-width="2"/>'


def _compact(shots: int) -> str:
    if shots >= MILLION:
        return f"{shots / MILLION:g}M"
    return f"{shots / THOUSAND:g}k" if shots >= THOUSAND else str(shots)


def _line(  # noqa: PLR0913
    x1: float, y1: float, x2: float, y2: float, *, stroke: str, width: float
) -> str:
    ends = f'x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"'
    return f'<line {ends} stroke="{stroke}" stroke-width="{width}"/>'


def _text(  # noqa: PLR0913
    x: float, y: float, text: str, fill: str, size: float, *, anchor: str = "start"
) -> str:
    place = f'x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}"'
    return f'<text {place} fill="{fill}" font-size="{size}">{escape(text)}</text>'


def main(argv: Sequence[str] | None = None) -> int:
    """Write the figure in both themes from the chains given, and print where each went.

    Args:
        argv: ``[--out dir] [--name stem] <chain>...``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when a chain is missing or they cannot be one figure.
    """
    parser = argparse.ArgumentParser(
        prog="learning-curve", description="draw the readme's learning curve from chains"
    )
    parser.add_argument("chains", nargs="+", help="s3://bucket/chains/<run> or a directory")
    parser.add_argument(
        "--out", type=Path, default=Path("docs/figures"), help="directory for the SVGs"
    )
    parser.add_argument("--name", default="learning-curve", help="file stem before the theme")
    args = parser.parse_args(argv)
    try:
        curves = [read_chain(chain) for chain in args.chains]
        figures = {theme: draw(theme, curves) for theme in PALETTES}
    except (FileNotFoundError, KeyError, ValueError) as error:
        print(f"learning-curve: {error}", file=sys.stderr)
        return 2
    # Both themes or neither: the README shows one or the other by the reader's setting.
    args.out.mkdir(parents=True, exist_ok=True)
    for theme, svg in figures.items():
        path = args.out / f"{args.name}-{theme}.svg"
        path.write_text(svg + "\n")
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
