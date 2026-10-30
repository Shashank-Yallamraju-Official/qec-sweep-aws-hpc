from mpi.account import Account


def test_gates_are_counted_by_kind_and_compute_time_adds_up() -> None:
    account = Account()
    account.gate(far=False, compute_seconds=0.5)
    account.gate(far=True, compute_seconds=0.25)
    account.gate(far=True, compute_seconds=0.25)
    assert account.as_dict() == {
        "local_gates": 1,
        "far_gates": 2,
        "compute_seconds": 1.0,
        "exchange_seconds": 0.0,
    }
