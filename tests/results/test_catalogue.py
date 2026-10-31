from pathlib import Path

import pyarrow.parquet as pq
import pytest

from results.catalogue import CATALOGUE, SCHEMA, catalogue, main, write_catalogue
from results.store import LocalStore


def test_catalogue_has_one_row_per_run_oldest_first(store: LocalStore) -> None:
    table = catalogue(store)
    assert table.schema == SCHEMA
    assert table.column("run").to_pylist() == [
        "20261030T001136Z",
        "20261030T120000Z",
        "20261030T231737Z",
    ]
    assert table.column("kind").to_pylist() == ["sweeps", "statevector", "sweeps"]


def test_catalogue_counts_the_cells_beside_each_record(store: LocalStore) -> None:
    table = catalogue(store)
    assert table.column("cells").to_pylist() == [2, 0, 3]


def test_catalogue_names_each_run_by_its_full_address(store: LocalStore) -> None:
    table = catalogue(store)
    assert table.column("key").to_pylist()[-1] == store.uri("sweeps/20261030T231737Z")
    assert table.column("parents").to_pylist()[-1] == ["s3://bucket/sweeps/20261030T001136Z"]


def test_a_thin_record_catalogues_with_nulls(store: LocalStore) -> None:
    thin = catalogue(store).slice(0, 1).to_pylist()[0]
    assert thin["image_digest"] is None
    assert thin["seed"] is None
    assert thin["parents"] == []


def test_write_catalogue_puts_the_table_into_the_store(store: LocalStore) -> None:
    uri = write_catalogue(store, catalogue(store))
    assert uri == store.uri(CATALOGUE)
    assert pq.read_table(uri).num_rows == 3


def test_the_command_says_how_many_runs_it_found(
    store: LocalStore, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(store.root)]) == 0
    assert capsys.readouterr().out.strip() == f"3 runs -> {store.uri(CATALOGUE)}"


def test_the_command_reports_an_empty_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path)]) == 2
    assert "no run.json" in capsys.readouterr().err
