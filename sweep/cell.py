"""The unit of work: one cell of the sweep grid."""

from __future__ import annotations

from dataclasses import dataclass

MIN_DISTANCE = 3


@dataclass(frozen=True)
class Cell:
    """One point of the sweep grid: a surface code of this distance under this noise.

    Attributes:
        distance: Code distance, odd and at least three.
        noise: Physical error rate applied to every noise channel, in (0, 1).
        shots: Number of syndrome samples to decode.
    """

    distance: int
    noise: float
    shots: int

    def __post_init__(self) -> None:
        if self.distance < MIN_DISTANCE or self.distance % 2 == 0:
            msg = f"distance must be odd and at least {MIN_DISTANCE}, not {self.distance}"
            raise ValueError(msg)
        if not 0 < self.noise < 1:
            msg = f"noise must be between 0 and 1 exclusive, not {self.noise}"
            raise ValueError(msg)
        if self.shots <= 0:
            msg = f"shots must be positive, not {self.shots}"
            raise ValueError(msg)

    @property
    def name(self) -> str:
        """File-safe name that is unique per cell, such as ``d5_p0.001_s100000``."""
        return f"d{self.distance}_p{self.noise!r}_s{self.shots}"
