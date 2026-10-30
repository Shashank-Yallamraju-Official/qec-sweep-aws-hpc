import numpy as np
import pytest

from mpi.exchange import Alone


def test_alone_is_rank_zero_of_one() -> None:
    assert (Alone().rank, Alone().size) == (0, 1)


def test_alone_has_no_peer_to_swap_with() -> None:
    with pytest.raises(LookupError, match="cannot swap"):
        Alone().swap(np.zeros(2, dtype=np.complex128), 1)
