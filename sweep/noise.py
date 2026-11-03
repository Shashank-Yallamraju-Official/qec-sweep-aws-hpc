"""The circuits a cell is simulated with: the surface-code memory under each noise model."""

from __future__ import annotations

from typing import Literal, get_args

import stim

from sweep.cell import Cell

Noise = Literal["depolarising", "correlated"]
NOISE_MODELS: tuple[Noise, ...] = get_args(Noise)
"""``depolarising`` is Stim's circuit-level model, the one the sweep has always decoded
under. ``correlated`` keeps every channel but turns the per-round data noise into pure
Y errors: a Y flips both an X and a Z stabiliser at once, and matching, which decodes
the two kinds apart, is known to do worse on it than a decoder that sees both.
"""
DEPOLARISING: Noise = "depolarising"


def memory_circuit(cell: Cell) -> stim.Circuit:
    """Stim's rotated memory-Z surface code for a cell.

    As many rounds as the distance, circuit-level depolarising noise at the cell's
    rate on every channel.
    """
    return stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=cell.distance,
        rounds=cell.distance,
        after_clifford_depolarization=cell.noise,
        before_round_data_depolarization=cell.noise,
        before_measure_flip_probability=cell.noise,
        after_reset_flip_probability=cell.noise,
    )


def noisy_circuit(cell: Cell, noise: Noise = DEPOLARISING) -> stim.Circuit:
    """The cell's memory circuit under a noise model; see ``NOISE_MODELS``."""
    circuit = memory_circuit(cell)
    if noise == DEPOLARISING:
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
