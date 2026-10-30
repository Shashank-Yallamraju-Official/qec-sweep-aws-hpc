"""Where a shard's time goes: gates applied, and seconds computing against seconds exchanging."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Account:
    """What a shard has spent since it was made.

    Attributes:
        local_gates: Gates that touched local qubits only.
        far_gates: Gates that touched a global qubit and so needed an exchange.
        compute_seconds: Time applying matrices to amplitudes.
        exchange_seconds: Time swapping slices with other ranks.
    """

    local_gates: int = 0
    far_gates: int = 0
    compute_seconds: float = 0.0
    exchange_seconds: float = 0.0

    def gate(self, *, far: bool, compute_seconds: float) -> None:
        """Count one gate and the time its matrix took, exchanges aside."""
        if far:
            self.far_gates += 1
        else:
            self.local_gates += 1
        self.compute_seconds += compute_seconds

    def as_dict(self) -> dict[str, int | float]:
        """The account as plain values, for a record."""
        return asdict(self)
