import json
from datetime import UTC, datetime

import pytest

from results.run import parse_record, read_cells, read_record
from results.store import LocalStore
from tests.results.conftest import FULL_RECORD, STATEVECTOR_RECORD, THIN_RECORD


def test_a_full_record_keeps_every_audit_field() -> None:
    record = parse_record("s3://b/sweeps/x", "sweeps", json.dumps(FULL_RECORD))
    assert record.image_digest == "sha256:9d217f8c"
    assert record.commit == "207f3e5"
    assert record.seed == 7
    assert record.parents == ("s3://bucket/sweeps/20261030T001136Z",)
    assert json.loads(record.jobs) == {"array": 41, "sync": 42}
    assert record.finished == datetime(2026, 10, 30, 23, 27, 37, tzinfo=UTC)
    assert json.loads(record.parameters) == {}


def test_a_thin_record_leaves_what_it_lacks_empty() -> None:
    record = parse_record("s3://b/sweeps/y", "sweeps", json.dumps(THIN_RECORD))
    assert (record.image_digest, record.commit, record.seed, record.nodes_used) == (None,) * 4
    assert record.parents == ()
    assert record.jobs == "{}"


def test_what_only_one_kind_of_run_records_lands_in_parameters() -> None:
    record = parse_record("s3://b/statevector/z", "statevector", json.dumps(STATEVECTOR_RECORD))
    assert json.loads(record.parameters) == {"layers": 6, "qubits": 25, "ranks_per_node": 2}
    assert record.nodes is None


def test_a_record_without_a_run_name_is_reported_by_address() -> None:
    with pytest.raises(ValueError, match="s3://b/sweeps/y record lacks queue, run"):
        parse_record("s3://b/sweeps/y", "sweeps", json.dumps({"submitted": "2026-10-30T00:00:00Z"}))


def test_an_unfinished_record_has_no_finish() -> None:
    record = parse_record("k", "sweeps", json.dumps({**THIN_RECORD, "finished": None}))
    assert record.finished is None


def test_read_record_takes_the_kind_from_the_key(store: LocalStore) -> None:
    record = read_record(store, "statevector/20261030T120000Z")
    assert (record.kind, record.run) == ("statevector", "20261030T120000Z")
    assert record.key == store.uri("statevector/20261030T120000Z")


def test_read_cells_folds_the_run_s_cells_and_nothing_else(store: LocalStore) -> None:
    cells = read_cells(store, "sweeps/20261030T231737Z")
    assert set(cells.column("distance").to_pylist()) == {3, 5, 7}
    assert set(cells.column("seed").to_pylist()) == {7}


def test_read_cells_reports_a_run_without_cells(store: LocalStore) -> None:
    with pytest.raises(FileNotFoundError, match="no cells under"):
        read_cells(store, "statevector/20261030T120000Z")
