"""Labelled syndrome histories for training: the ``decoder-sample`` command.

One call samples one cell under one noise model with one seed and writes a
compressed ``.npz`` named by all three, holding the detection events arranged
round by round and the observable flip each shot ended with.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

import numpy as np
import stim

from sweep.cell import Cell
from sweep.decode import memory_circuit

Noise = Literal["depolarising", "correlated"]
NOISE_MODELS: tuple[Noise, ...] = get_args(Noise)
"""``depolarising`` is Stim's circuit-level model, the one the sweep decodes under.
``correlated`` keeps every channel but turns the per-round data noise into pure Y
errors: a Y flips both an X and a Z stabiliser at once, and matching, which decodes
the two kinds apart, is known to do worse on it than a decoder that sees both.
"""


@dataclass(frozen=True)
class Layout:
    """Where each of a circuit's detectors sits in a round-by-stabiliser grid.

    Attributes:
        rounds: Time slices, one per measurement round plus the final data readout.
        stabilisers: Positions in a slice, one per stabiliser of the code.
        slots: The detector indices, in the order the two arrays below describe them.
        rounds_of: Each detector's slice.
        stabilisers_of: Each detector's position.
    """

    rounds: int
    stabilisers: int
    slots: tuple[int, ...]
    rounds_of: tuple[int, ...]
    stabilisers_of: tuple[int, ...]


@dataclass(frozen=True)
class Samples:
    """One cell's labelled syndrome histories.

    Attributes:
        cell: The cell sampled.
        seed: The sampler seed.
        noise: The noise model.
        circuit: The circuit the samples came from.
        detectors: Detection events, ``(shots, rounds, stabilisers)``, 0 or 1; a slot
            with no detector in the circuit stays 0.
        flips: Whether the logical observable flipped, ``(shots,)``, 0 or 1.
    """

    cell: Cell
    seed: int
    noise: Noise
    circuit: stim.Circuit
    detectors: np.ndarray[tuple[int, int, int], np.dtype[np.uint8]]
    flips: np.ndarray[tuple[int], np.dtype[np.uint8]]

    @property
    def name(self) -> str:
        """File-safe name unique per cell, seed and noise model."""
        return f"{self.cell.name}_seed{self.seed}_{self.noise}"


def layout(circuit: stim.Circuit) -> Layout:
    """Place a generated circuit's detectors by their coordinates.

    Stim gives each detector of a generated surface-code circuit an ``(x, y, t)``
    coordinate; ``t`` is the round and ``(x, y)`` the stabiliser it checks.
    """
    coordinates = circuit.get_detector_coordinates()
    positions = sorted({(x, y) for x, y, _ in coordinates.values()})
    position_of = {p: i for i, p in enumerate(positions)}
    slots = tuple(sorted(coordinates))
    return Layout(
        rounds=int(max(t for _, _, t in coordinates.values())) + 1,
        stabilisers=len(positions),
        slots=slots,
        rounds_of=tuple(int(coordinates[d][2]) for d in slots),
        stabilisers_of=tuple(position_of[(coordinates[d][0], coordinates[d][1])] for d in slots),
    )


def noisy_circuit(cell: Cell, noise: Noise) -> stim.Circuit:
    """The cell's memory circuit under a noise model; see ``NOISE_MODELS``."""
    circuit = memory_circuit(cell)
    if noise == "depolarising":
        return circuit
    return _with_y_data_noise(circuit)


def _with_y_data_noise(circuit: stim.Circuit) -> stim.Circuit:
    out = stim.Circuit()
    for instruction in circuit:
        if isinstance(instruction, stim.CircuitRepeatBlock):
            out.append(
                stim.CircuitRepeatBlock(
                    instruction.repeat_count, _with_y_data_noise(instruction.body_copy())
                )
            )
        elif instruction.name == "DEPOLARIZE1":
            out.append("Y_ERROR", instruction.targets_copy(), instruction.gate_args_copy())
        else:
            out.append(instruction)
    return out


def sample(cell: Cell, seed: int = 0, noise: Noise = "depolarising") -> Samples:
    """Sample a cell's syndromes and arrange them round by round."""
    circuit = noisy_circuit(cell, noise)
    grid = layout(circuit)
    events, observables = circuit.compile_detector_sampler(seed=seed).sample(
        cell.shots, separate_observables=True
    )
    detectors = np.zeros((cell.shots, grid.rounds, grid.stabilisers), dtype=np.uint8)
    detectors[:, grid.rounds_of, grid.stabilisers_of] = events[:, grid.slots]
    return Samples(
        cell=cell,
        seed=seed,
        noise=noise,
        circuit=circuit,
        detectors=detectors,
        flips=observables[:, 0].astype(np.uint8),
    )


def write(samples: Samples, out_dir: Path) -> Path:
    """Write the samples as one compressed ``.npz`` named by cell, seed and noise."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{samples.name}.npz"
    cell = samples.cell
    np.savez_compressed(
        path,
        detectors=samples.detectors,
        flips=samples.flips,
        cell=np.array([cell.distance, cell.noise, cell.shots]),
        seed=np.array(samples.seed),
        noise=np.array(samples.noise),
    )
    return path


def read(path: Path) -> Samples:
    """Read back a file written by ``write()``, rebuilding its circuit."""
    with np.load(path) as data:
        distance, noise_rate, shots = data["cell"]
        cell = Cell(int(distance), float(noise_rate), int(shots))
        noise = str(data["noise"])
        if noise not in NOISE_MODELS:
            msg = f"{path} names an unknown noise model {noise}"
            raise ValueError(msg)
        model: Noise = "correlated" if noise == "correlated" else "depolarising"
        return Samples(
            cell=cell,
            seed=int(data["seed"]),
            noise=model,
            circuit=noisy_circuit(cell, model),
            detectors=data["detectors"],
            flips=data["flips"],
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Sample one cell and print the file written.

    Args:
        argv: ``--d --p --shots [--seed] [--noise] --out``; ``None`` reads ``sys.argv``.

    Returns:
        Exit status 0.
    """
    parser = argparse.ArgumentParser(
        prog="decoder-sample", description="sample labelled syndrome histories for one cell"
    )
    parser.add_argument("--d", type=int, required=True, help="code distance")
    parser.add_argument("--p", type=float, required=True, help="physical error rate")
    parser.add_argument("--shots", type=int, required=True, help="shots to sample")
    parser.add_argument("--seed", type=int, default=0, help="sampler seed")
    parser.add_argument("--noise", choices=NOISE_MODELS, default="depolarising", help="noise model")
    parser.add_argument("--out", type=Path, required=True, help="directory for the file")
    args = parser.parse_args(argv)
    cell = Cell(distance=args.d, noise=args.p, shots=args.shots)
    print(write(sample(cell, seed=args.seed, noise=args.noise), args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
