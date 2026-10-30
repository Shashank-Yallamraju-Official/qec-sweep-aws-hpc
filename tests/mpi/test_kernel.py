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


@pytest.mark.parametrize(("gate", "bits"), [(H, [5]), (T, [4]), (CNOT, [5, 1]), (CZ, [5, 4])])
def test_keeping_one_slot_writes_that_row_and_leaves_the_others(
    native: Kernel, gate: Gate, bits: list[int]
) -> None:
    whole, kept = stack(4, 4), stack(4, 4)
    before = kept.copy()
    native.mix(whole, gate.matrix, bits)
    native.mix(kept, gate.matrix, bits, keep=2)
    assert np.allclose(kept[2], whole[2])
    assert np.array_equal(kept[[0, 1, 3]], before[[0, 1, 3]])


def test_the_native_pass_works_in_place_on_the_stack(native: Kernel) -> None:
    group = stack(2, 3)
    before = group.copy()
    native.mix(group, H.matrix, [1])
    assert not np.allclose(group, before)
    native.mix(group, H.matrix, [1])
    assert np.allclose(group, before)


@pytest.mark.parametrize(
    "bad", [stack(2, 3)[:, ::2], np.zeros((2, 8)), np.zeros((2, 8), dtype=np.complex64)]
)
def test_the_native_pass_refuses_a_strided_or_differently_typed_stack(
    native: Kernel, bad: Amplitudes
) -> None:
    with pytest.raises(ValueError, match="contiguous complex128"):
        native.mix(bad, H.matrix, [0])


def test_the_kernel_names_itself(native: Kernel) -> None:
    assert (Kernel(None).name, native.name) == ("numpy", "native")
