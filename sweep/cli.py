from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sweep.cell import Cell
from sweep.decode import decode
from sweep.parquet import write


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sweep", description="sample and decode one surface-code cell"
    )
    parser.add_argument("--d", type=int, required=True, help="code distance, odd")
    parser.add_argument("--p", type=float, required=True, help="physical noise rate")
    parser.add_argument("--shots", type=int, required=True, help="samples to decode")
    parser.add_argument("--out", type=Path, required=True, help="directory for the result")
    parser.add_argument("--seed", type=int, default=0, help="sampler seed")
    args = parser.parse_args(argv)
    try:
        cell = Cell(distance=args.d, noise=args.p, shots=args.shots)
    except ValueError as error:
        print(f"sweep: {error}", file=sys.stderr)
        return 2
    print(write(decode(cell, seed=args.seed), args.out))
    return 0
