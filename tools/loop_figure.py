"""The README's figure: one change, from a pull request to a comparison, as a sequence.

Six lifelines, each a named system, and twelve messages in the order they happen,
drawn as SVG in a light and a dark theme so GitHub shows the reader the right one.
The marks on the lifelines are the official ones, checked in under
``docs/figures/marks``: GitHub's Invertocat under GitHub's logo guidelines, the AWS
Architecture Icons under their terms for architecture diagrams, and the author's
avatar. They are embedded, so the figure is one file with nothing to fetch.
"""

from __future__ import annotations

import argparse
import base64
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

LIFELINES = (
    "Researcher",
    "GitHub",
    "GitHub Actions",
    "AWS ParallelCluster",
    "Amazon S3",
    "GitHub Pages",
)
MARKS = {
    "Researcher": "researcher.jpg",
    "GitHub": "github-{ink}.svg",
    "GitHub Actions": "github-{ink}.svg",
    "AWS ParallelCluster": "aws-parallelcluster.svg",
    "Amazon S3": "amazon-s3.svg",
    "GitHub Pages": "github-{ink}.svg",
}


Kind = Literal["request", "reply", "result"]
KINDS: tuple[Kind, ...] = get_args(Kind)
MIMES = {".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


@dataclass(frozen=True)
class Message:
    """One arrow: who acts on whom, what the label says, and what kind of arrow it is.

    Attributes:
        sender: Index of the lifeline the arrow leaves.
        receiver: Index of the lifeline it reaches; the sender itself for a self-message.
        label: The words above the arrow.
        kind: ``request`` for one system acting on another, ``reply`` for an answer,
            drawn dashed with an open head, or ``result`` for a result on its way to
            the reader, drawn in the accent.
    """

    sender: int
    receiver: int
    label: str
    kind: Kind = "request"

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            msg = f"kind must be one of {', '.join(KINDS)}, not {self.kind}"
            raise ValueError(msg)


MESSAGES = (
    Message(0, 1, "open pull request"),
    Message(1, 2, "run workflows"),
    Message(2, 3, "validate cluster.yaml, run smoke job"),
    Message(2, 1, "checks pass", kind="reply"),
    Message(0, 1, "merge"),
    Message(1, 2, "run deploy workflow"),
    Message(2, 3, "install job scripts, update cluster"),
    Message(0, 3, "sbatch a sweep"),
    Message(3, 3, "boot nodes, decode cells, scale to zero"),
    Message(3, 4, "put run.json and cells", kind="result"),
    Message(2, 5, "publish site with a snapshot from S3", kind="result"),
    Message(0, 5, "compare two runs", kind="result"),
)
PHASES = (("Change", 0, 3), ("Ship", 4, 6), ("Run", 7, 9), ("Compare", 10, 11))
PALETTES = {
    "light": {
        "bg": "#ffffff", "band": "#f6f6f7", "text": "#1b1b1f", "muted": "#8b8b92",
        "line": "#c9c9ce", "msg": "#2c2c31", "arrow": "#4a4a52", "accent": "#2a78d6",
        "num": "#b0b0b6", "frame": "#e3e3e8",
    },
    "dark": {
        "bg": "#0e0f12", "band": "#15171b", "text": "#ececf0", "muted": "#7c7c86",
        "line": "#34353c", "msg": "#d2d2d8", "arrow": "#a5a5ae", "accent": "#5a9cf0",
        "num": "#5e5e68", "frame": "#2a2b31",
    },
}  # fmt: skip
WIDTH = 1240
X = (130, 330, 530, 730, 930, 1130)
HEAD_Y, TOP, STEP, ICON = 64, 160, 52, 52
FONT = "-apple-system, Inter, 'Helvetica Neue', 'Segoe UI', Arial, sans-serif"
INK = {"light": "black", "dark": "white"}
HEAD = (
    'markerWidth="9" markerHeight="9" refX="8" refY="4.5" '
    'orient="auto" markerUnits="userSpaceOnUse"'
)
KEY = (
    ("request", "a request: one system acts on another", 262),
    ("reply", "a reply", 96),
    ("result", "a result on its way to the reader", 236),
    ("lifeline", "a system's lifeline, time runs down", 240),
    ("step", "a step the text refers to", 200),
)


def embed(path: Path) -> str:
    """A mark as a data URI, so the figure carries it.

    Raises:
        FileNotFoundError: Naming the mark that is missing.
        ValueError: For a file type no mark is kept as.
    """
    if not path.exists():
        msg = f"no mark at {path}"
        raise FileNotFoundError(msg)
    if path.suffix not in MIMES:
        msg = f"no mark can be a {path.suffix.lstrip('.')} file: {path}"
        raise ValueError(msg)
    mime = MIMES[path.suffix]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def draw(theme: str, marks: Path) -> str:
    """The figure in one theme, as SVG text."""
    c = PALETTES[theme]
    bottom = TOP + STEP * len(MESSAGES) + 10
    key_y = bottom + 26
    height = key_y + 62
    size = f'viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}"'
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" {size} font-family="{FONT}">',
        f'<rect width="{WIDTH}" height="{height}" fill="{c["bg"]}"/>',
        _defs(theme, c),
        *_phases(c),
        *_lifelines(theme, c, marks, bottom),
        *_messages(theme, c),
        *_key(theme, c, key_y),
        "</svg>",
    ]
    return "\n".join(parts)


def _defs(theme: str, c: dict[str, str]) -> str:
    head = 'd="M0,0 L9,4.5 L0,9 z"'
    return "".join(
        [
            "<defs>",
            f'<clipPath id="avatar-{theme}">',
            f'<circle cx="{X[0]}" cy="{HEAD_Y}" r="{ICON / 2}"/></clipPath>',
            f'<marker id="request-{theme}" {HEAD}><path {head} fill="{c["arrow"]}"/></marker>',
            f'<marker id="reply-{theme}" {HEAD}>',
            f'<path {head} fill="none" stroke="{c["arrow"]}" stroke-width="1.2"/></marker>',
            f'<marker id="result-{theme}" {HEAD}><path {head} fill="{c["accent"]}"/></marker>',
            "</defs>",
        ]
    )


def _phases(c: dict[str, str]) -> list[str]:
    parts = []
    for i, (label, first, last) in enumerate(PHASES):
        y0, y1 = TOP + STEP * first - 30, TOP + STEP * last + 14
        if i % 2 == 0:
            parts.append(_rect(40, y0, WIDTH - 60, y1 - y0, fill=c["band"]))
        parts.append(_label(52, y0 + 16, label.upper(), c["muted"]))
    return parts


def _lifelines(theme: str, c: dict[str, str], marks: Path, bottom: float) -> list[str]:
    parts = []
    for x, name in zip(X, LIFELINES, strict=True):
        mark = embed(marks / MARKS[name].format(ink=INK[theme]))
        parts.append(_line(x, HEAD_Y + 62, x, bottom, stroke=c["line"], width=1, dash="3 5"))
        clip = f' clip-path="url(#avatar-{theme})"' if name == LIFELINES[0] else ""
        corner = f'x="{x - ICON / 2}" y="{HEAD_Y - ICON / 2}" width="{ICON}" height="{ICON}"'
        parts.append(f'<image href="{mark}" {corner}{clip}/>')
        if clip:
            ring = f'cx="{x}" cy="{HEAD_Y}" r="{ICON / 2}" fill="none" stroke="{c["frame"]}"'
            parts.append(f"<circle {ring}/>")
        parts.append(_text(x, HEAD_Y + 50, name, c["text"], 13, anchor="middle", weight=600))
    return parts


def _messages(theme: str, c: dict[str, str]) -> list[str]:
    parts = []
    for i, m in enumerate(MESSAGES):
        y = TOP + STEP * i
        parts.append(_step(98, y, i + 1, c["num"]))
        xa, xb = X[m.sender], X[m.receiver]
        stroke = c["accent"] if m.kind == "result" else c["arrow"]
        marker = f'marker-end="url(#{m.kind}-{theme})"'
        if m.sender == m.receiver:
            turn = f"M{xa},{y} L{xa + 70},{y} L{xa + 70},{y + 22} L{xa + 6},{y + 22}"
            parts.append(
                f'<path d="{turn}" fill="none" stroke="{stroke}" stroke-width="1.2" {marker}/>'
            )
            parts.append(_text(xa + 82, y + 16, m.label, c["msg"], 12))
            continue
        gap = 8 if xb > xa else -8
        width = 1.5 if m.kind == "result" else 1.2
        dash = "5 4" if m.kind == "reply" else None
        parts.append(
            _line(xa + gap, y, xb - gap, y, stroke=stroke, width=width, dash=dash, marker=marker)
        )
        parts.append(_text((xa + xb) / 2, y - 8, m.label, c["msg"], 12, anchor="middle"))
    return parts


def _key(theme: str, c: dict[str, str], key_y: float) -> list[str]:
    ky = key_y + 26
    parts = [
        _rect(40, key_y, WIDTH - 60, 50, fill="none", stroke=c["frame"]),
        _label(56, key_y + 30, "KEY", c["muted"]),
    ]
    x = 120
    for kind, label, width in KEY:
        marker = f'marker-end="url(#{kind}-{theme})"'
        if kind == "request":
            parts.append(_line(x, ky, x + 44, ky, stroke=c["arrow"], width=1.2, marker=marker))
        elif kind == "reply":
            parts.append(
                _line(x, ky, x + 44, ky, stroke=c["arrow"], width=1.2, dash="5 4", marker=marker)
            )
        elif kind == "result":
            parts.append(_line(x, ky, x + 44, ky, stroke=c["accent"], width=1.5, marker=marker))
        elif kind == "lifeline":
            parts.append(
                _line(x + 22, ky - 12, x + 22, ky + 12, stroke=c["line"], width=1, dash="3 5")
            )
        else:
            parts.append(_step(x + 22, ky, 7, c["num"]))
        parts.append(_text(x + 54, ky + 4, label, c["msg"], 11))
        x += width
    return parts


def _rect(  # noqa: PLR0913
    x: float, y: float, w: float, h: float, *, fill: str, stroke: str | None = None
) -> str:
    edge = f' stroke="{stroke}"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}"{edge}/>'


def _line(  # noqa: PLR0913
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    stroke: str,
    width: float,
    dash: str | None = None,
    marker: str = "",
) -> str:
    dashed = f' stroke-dasharray="{dash}"' if dash else ""
    ends = f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"'
    return f'<line {ends} stroke="{stroke}" stroke-width="{width}"{dashed} {marker}/>'


def _text(  # noqa: PLR0913
    x: float,
    y: float,
    text: str,
    fill: str,
    size: float,
    *,
    anchor: str = "start",
    weight: int | None = None,
) -> str:
    bold = f' font-weight="{weight}"' if weight else ""
    place = f'x="{x}" y="{y}" text-anchor="{anchor}"'
    return f'<text {place} fill="{fill}" font-size="{size}"{bold}>{text}</text>'


def _label(x: float, y: float, text: str, colour: str) -> str:
    style = f'fill="{colour}" font-size="10" letter-spacing="1.6" font-weight="600"'
    return f'<text x="{x}" y="{y}" {style}>{text}</text>'


def _step(x: float, y: float, number: int, colour: str) -> str:
    ring = f'<circle cx="{x}" cy="{y}" r="9" fill="none" stroke="{colour}" stroke-width="1"/>'
    return ring + _text(x, y + 3.5, str(number), colour, 9.5, anchor="middle", weight=600)


def main(argv: Sequence[str] | None = None) -> int:
    """Write the figure in both themes and print where each went.

    Args:
        argv: ``[--out dir] [--marks dir]``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when a mark is missing or of an unknown type.
    """
    parser = argparse.ArgumentParser(
        prog="loop-figure", description="draw the readme's loop figure"
    )
    parser.add_argument(
        "--out", type=Path, default=Path("docs/figures"), help="directory for the SVGs"
    )
    parser.add_argument(
        "--marks", type=Path, default=Path("docs/figures/marks"), help="directory of the marks"
    )
    args = parser.parse_args(argv)
    try:
        figures = {theme: draw(theme, args.marks) for theme in PALETTES}
    except (FileNotFoundError, ValueError) as error:
        print(f"loop-figure: {error}", file=sys.stderr)
        return 2
    # Both themes or neither: the README shows one or the other by the reader's setting.
    args.out.mkdir(parents=True, exist_ok=True)
    for theme, svg in figures.items():
        path = args.out / f"loop-{theme}.svg"
        path.write_text(svg + "\n")
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
