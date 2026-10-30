"""The gates a circuit is built from, each a matrix over the qubits it is applied to."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

type Matrix = NDArray[np.complex128]


@dataclass(frozen=True, eq=False)
class Gate:
    """A unitary on one or two qubits.

    The matrix is over the basis of the qubits the gate is applied to, first
    qubit most significant: a gate on ``(a, b)`` is over ``|a b>``.

    Attributes:
        name: Short name for records and logs.
        matrix: The unitary, square with a power-of-two side.
    """

    name: str
    matrix: Matrix

    def __post_init__(self) -> None:
        side = self.matrix.shape[0]
        if self.matrix.shape != (side, side) or side < 2 or side & (side - 1):  # noqa: PLR2004
            msg = f"{self.name}: a gate is square with a power-of-two side, not {self.matrix.shape}"
            raise ValueError(msg)

    @property
    def arity(self) -> int:
        """Number of qubits the gate acts on."""
        return len(self.matrix).bit_length() - 1


H = Gate("h", np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2))
T = Gate("t", np.diag([1, np.exp(1j * np.pi / 4)]).astype(np.complex128))
X = Gate("x", np.array([[0, 1], [1, 0]], dtype=np.complex128))
