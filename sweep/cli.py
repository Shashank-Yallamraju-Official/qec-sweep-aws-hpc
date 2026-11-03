"""The ``sweep`` command: one call, one cell, one Parquet file.

The decoder is a choice of the call: PyMatching by default, or the trained model
behind ``--decoder learned --model <decoder.pt>``, which needs torch and so runs in
the training image. The noise model is a choice too; both are written into the cell.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sweep.cell import Cell
from sweep.decode import MATCHING, CellResult, decode
from sweep.grid import GRID
from sweep.noise import DEPOLARISING, NOISE_MODELS, Noise
from sweep.parquet import write

LEARNED = "learned"
DECODERS = (MATCHING, LEARNED)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one cell from command-line arguments and print the path written.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        Exit status: 0 on success, 2 when the cell or the decoder choice is invalid.
    """
    parser = argparse.ArgumentParser(
        prog="sweep", description="sample and decode one surface-code cell"
    )
    parser.add_argument("--d", type=int, help="code distance, odd")
    parser.add_argument("--p", type=float, help="physical noise rate")
    parser.add_argument("--shots", type=int, help="samples to decode")
    parser.add_argument(
        "--index", type=int, help="a cell of the sweep grid, instead of --d/--p/--shots"
    )
    parser.add_argument("--out", type=Path, required=True, help="directory for the result")
    parser.add_argument("--seed", type=int, default=0, help="sampler seed")
    parser.add_argument("--noise", choices=NOISE_MODELS, default=DEPOLARISING, help="noise model")
    parser.add_argument("--decoder", choices=DECODERS, default=MATCHING, help="what decodes")
    parser.add_argument("--model", type=Path, help="the trained model, for the learned decoder")
    args = parser.parse_args(argv)
    try:
        cell = _cell(args)
        result = _decode(cell, args)
    except (ValueError, IndexError) as error:
        print(f"sweep: {error}", file=sys.stderr)
        return 2
    print(write(result, args.out))
    return 0


def _cell(args: argparse.Namespace) -> Cell:
    explicit = (args.d, args.p, args.shots)
    if args.index is not None and any(v is not None for v in explicit):
        msg = "--index names a cell by itself; drop --d, --p and --shots"
        raise ValueError(msg)
    if args.index is not None:
        return GRID.cell(args.index)
    if None in explicit:
        msg = "give --index, or all of --d, --p and --shots"
        raise ValueError(msg)
    return Cell(distance=args.d, noise=args.p, shots=args.shots)


def _decode(cell: Cell, args: argparse.Namespace) -> CellResult:
    noise: Noise = args.noise
    if args.decoder == MATCHING:
        if args.model is not None:
            msg = "--model goes with --decoder learned; matching takes no model"
            raise ValueError(msg)
        return decode(cell, seed=args.seed, noise=noise)
    if args.model is None:
        msg = "the learned decoder needs --model, the decoder.pt a training run wrote"
        raise ValueError(msg)
    # Only the learned decoder needs torch, which the sweep image does not carry.
    from decoder.evaluate import decode as decode_learned  # noqa: PLC0415

    return decode_learned(cell, args.model, seed=args.seed, noise=noise)
