"""The gate kernel: one C++ pass over the amplitudes when its library is built, else numpy."""

from __future__ import annotations

import ctypes
import subprocess
from pathlib import Path

import numpy as np

from mpi.exchange import Amplitudes
from mpi.gates import Matrix

SOURCE = Path(__file__).with_name("kernel.cpp")
LIBRARY = Path(__file__).with_name("libkernel.so")


def build(compiler: str = "c++") -> Path:
    """Compile the kernel beside this module and return the library's path."""
    command = [compiler, "-O3", "-shared", "-fPIC", "-o", str(LIBRARY), str(SOURCE)]
    subprocess.run(command, check=True)  # noqa: S603
    return LIBRARY


class Kernel:
    """Applies a gate matrix in place to a stack of slices, natively or with numpy."""

    def __init__(self, library: ctypes.CDLL | None) -> None:
        """Use ``library`` for the pass, or numpy when it is ``None``."""
        self._native = library
        if library is not None:
            library.mix.restype = None
            library.mix.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_int),
            ]

    @classmethod
    def load(cls) -> Kernel:
        """The built library if there is one, else numpy."""
        return cls(ctypes.CDLL(str(LIBRARY)) if LIBRARY.exists() else None)

    @property
    def name(self) -> str:
        """``native`` or ``numpy``, for the run's record."""
        return "numpy" if self._native is None else "native"

    def mix(self, group: Amplitudes, matrix: Matrix, bits: list[int]) -> None:
        """Apply ``matrix`` to ``group`` in place on index bits ``bits``, first most significant.

        ``group`` is a contiguous stack of slices; an index is the slot's bits
        above the slice's bits, so ``bits`` can name either.
        """
        if self._native is None:
            _mix_numpy(group, matrix, bits)
            return
        if not group.flags.c_contiguous:
            msg = "the stack must be one contiguous buffer"
            raise ValueError(msg)
        flat = group.reshape(-1)
        operator = np.ascontiguousarray(matrix, dtype=np.complex128)
        positions = (ctypes.c_int * len(bits))(*bits)
        self._native.mix(flat.ctypes.data, flat.size, operator.ctypes.data, len(bits), positions)


def _mix_numpy(group: Amplitudes, matrix: Matrix, bits: list[int]) -> None:
    qubits = group.size.bit_length() - 1
    tensor = group.reshape((2,) * qubits)
    axes = [qubits - 1 - bit for bit in bits]
    arity = len(bits)
    operator = matrix.reshape((2,) * (2 * arity))
    mixed = np.tensordot(operator, tensor, axes=(list(range(arity, 2 * arity)), axes))
    group[...] = np.moveaxis(mixed, list(range(arity)), axes).reshape(group.shape)


KERNEL = Kernel.load()
