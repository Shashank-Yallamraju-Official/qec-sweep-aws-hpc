import ctypes
import shutil

import numpy as np
import pytest

from mpi.exchange import Amplitudes
from mpi.gates import CNOT, CZ, Gate, H, T
from mpi.kernel import Kernel, build

pytestmark = pytest.mark.skipif(shutil.which("c++") is None, reason="needs a C++ compiler")


@pytest.fixture(scope="module")
def native() -> Kernel:
    return Kernel(ctypes.CDLL(str(build())))


def stack(slots: int, slice_qubits: int, seed: int = 3) -> Amplitudes:
    rng = np.random.default_rng(seed)
    shape = (slots, 1 << slice_qubits)
    return np.asarray(rng.normal(size=shape) + 1j * rng.normal(size=shape), dtype=np.complex128)


@pytest.mark.parametrize(
    ("gate", "bits"), [(H, [0]), (T, [3]), (H, [4]), (CNOT, [1, 3]), (CNOT, [5, 2]), (CZ, [4, 5])]
)
def test_the_native_pass_agrees_with_numpy(native: Kernel, gate: Gate, bits: list[int]) -> None:
    with_numpy, with_native = stack(4, 4), stack(4, 4)
    Kernel(None).mix(with_numpy, gate.matrix, bits)
    native.mix(with_native, gate.matrix, bits)
    assert np.allclose(with_native, with_numpy)


def test_the_native_pass_works_in_place_on_the_stack(native: Kernel) -> None:
    group = stack(2, 3)
    before = group.copy()
    native.mix(group, H.matrix, [1])
    assert not np.allclose(group, before)
    native.mix(group, H.matrix, [1])
    assert np.allclose(group, before)


def test_the_native_pass_refuses_a_strided_stack(native: Kernel) -> None:
    strided = stack(2, 3)[:, ::2]
    with pytest.raises(ValueError, match="contiguous"):
        native.mix(strided, H.matrix, [0])


def test_the_kernel_names_itself(native: Kernel) -> None:
    assert (Kernel(None).name, native.name) == ("numpy", "native")
