import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from results.compare import compare
from results.manifest import (
    Baseline,
    Manifest,
    admissible,
    describe,
    in_force,
    main,
    noise_of,
    read_manifest,
    resolve,
)
from results.run import read_cells, read_record
from results.store import LocalStore
from tests.results.conftest import FULL_RECORD, write_run
from tests.results.test_compare import cells

FULL = "sweeps/20261030T231737Z"


def manifest(store: LocalStore, run: str = FULL, **changes: object) -> Manifest:
    base = {"name": "pymatching", "decoder": "pymatching", "noise_model": "depolarising"}
    base |= {"run": store.uri(run), "image_digest": "sha256:9d217f8c"}
    return Manifest(**{**base, **changes})  # type: ignore[arg-type]


def write_manifest(path: Path, manifest: Manifest | dict[str, object]) -> Path:
    data = manifest if isinstance(manifest, dict) else manifest.__dict__
    path.write_text(json.dumps(data))
    return path


def test_read_manifest_takes_the_fields_and_nothing_else(tmp_path: Path, store: LocalStore) -> None:
    path = write_manifest(tmp_path / "m.json", manifest(store))
    assert read_manifest(path) == manifest(store)


def test_read_manifest_names_a_missing_field(tmp_path: Path) -> None:
    path = write_manifest(tmp_path / "m.json", {"name": "x", "decoder": "pymatching"})
    with pytest.raises(ValueError, match="lacks image_digest, noise_model, run"):
        read_manifest(path)


def test_read_manifest_refuses_a_field_it_does_not_know(tmp_path: Path, store: LocalStore) -> None:
    path = write_manifest(tmp_path / "m.json", {**manifest(store).__dict__, "stage": "prod"})
    with pytest.raises(ValueError, match="no manifest has: stage"):
        read_manifest(path)


def test_resolve_follows_the_run_to_its_record_and_cells(store: LocalStore) -> None:
    record, table = resolve(manifest(store))
    assert record.commit == "207f3e5"
    assert table.num_rows == 3


def test_resolve_refuses_a_digest_the_run_did_not_record(store: LocalStore) -> None:
    with pytest.raises(
        ValueError, match="recorded image sha256:9d217f8c, the manifest says sha256:x"
    ):
        resolve(manifest(store, image_digest="sha256:x"))


def test_resolve_refuses_a_run_that_never_recorded_a_digest(store: LocalStore) -> None:
    with pytest.raises(ValueError, match="recorded image none"):
        resolve(manifest(store, run="sweeps/20261030T001136Z"))


def test_resolve_refuses_a_run_under_another_noise_model(store: LocalStore) -> None:
    correlated = {**FULL_RECORD, "run": "20261031T000000Z", "noise": "correlated"}
    write_run(store.root, "evaluations/20261031T000000Z", correlated, {5: 12}, "correlated")
    with pytest.raises(
        ValueError, match="ran under correlated noise, the manifest says depolarising"
    ):
        resolve(manifest(store, run="evaluations/20261031T000000Z"))
    record, _ = resolve(
        manifest(store, run="evaluations/20261031T000000Z", noise_model="correlated")
    )
    assert record.run == "20261031T000000Z"


def learned(store: LocalStore, weights: bytes = b"weights", **changes: object) -> Manifest:
    """A learned manifest whose weights sit in a training run the judged run came from."""
    train = store.root / "train" / "20261031T000000Z"
    train.mkdir(parents=True, exist_ok=True)
    (train / "decoder.pt").write_bytes(weights)
    record = {
        **FULL_RECORD,
        "run": "20261031T000100Z",
        "noise": "correlated",
        "parents": [store.uri("train/20261031T000000Z")],
    }
    if not (store.root / "evaluations" / "20261031T000100Z").exists():
        write_run(store.root, "evaluations/20261031T000100Z", record, {5: 12}, "correlated")
    fields = {
        "name": "lstm",
        "decoder": "learned",
        "noise_model": "correlated",
        "run": store.uri("evaluations/20261031T000100Z"),
        "image_digest": "sha256:9d217f8c",
        "artifact": store.uri("train/20261031T000000Z/decoder.pt"),
        "artifact_sha256": hashlib.sha256(weights).hexdigest(),
    }
    return Manifest(**{**fields, **changes})  # type: ignore[arg-type]


def test_resolve_reads_a_learned_decoder_s_weights_and_holds_them_to_the_hash(
    store: LocalStore,
) -> None:
    record, table = resolve(learned(store))
    assert record.run == "20261031T000100Z"
    assert table.num_rows == 1
    with pytest.raises(ValueError, match=r"hashes to [0-9a-f]{64}, the manifest says 0abc"):
        resolve(learned(store, artifact_sha256="0abc"))


def test_resolve_refuses_weights_the_judged_run_did_not_come_from(store: LocalStore) -> None:
    elsewhere = store.root / "train" / "20261031T000200Z"
    elsewhere.mkdir(parents=True)
    (elsewhere / "decoder.pt").write_bytes(b"weights")
    with pytest.raises(ValueError, match=r"was not made from .*train/20261031T000200Z"):
        resolve(learned(store, artifact=store.uri("train/20261031T000200Z/decoder.pt")))


def test_resolve_refuses_a_learned_manifest_without_weights_and_matching_with(
    store: LocalStore,
) -> None:
    with pytest.raises(ValueError, match="name its weights"):
        resolve(learned(store, artifact=None, artifact_sha256=None))
    with pytest.raises(ValueError, match="matching and has no weights"):
        resolve(manifest(store, artifact=store.uri("train/x/decoder.pt")))


def test_resolve_reports_missing_weights_as_not_found(store: LocalStore) -> None:
    with pytest.raises(FileNotFoundError):
        resolve(learned(store, artifact=store.uri("train/20261031T000000Z/nowhere.pt")))


def _without_noise_column(store: LocalStore, key: str) -> None:
    for path in (store.root / key).glob("*.parquet"):
        table = pq.read_table(path)
        pq.write_table(table.drop_columns(["noise_model"]), path)


def test_noise_comes_from_the_cells_then_the_record_then_the_run_s_age(store: LocalStore) -> None:
    record = read_record(store, FULL)
    cells = read_cells(store, FULL)
    assert noise_of(record, cells) == "depolarising"
    _without_noise_column(store, FULL)
    assert noise_of(record, read_cells(store, FULL)) == "depolarising"
    recent = {**FULL_RECORD, "run": "20261105T000000Z", "submitted": "2026-11-05T00:00:00Z"}
    write_run(store.root, "sweeps/20261105T000000Z", recent, {3: 28})
    _without_noise_column(store, "sweeps/20261105T000000Z")
    assert (
        noise_of(
            read_record(store, "sweeps/20261105T000000Z"),
            read_cells(store, "sweeps/20261105T000000Z"),
        )
        is None
    )
    with pytest.raises(ValueError, match="recorded no noise model, the manifest says depolarising"):
        resolve(manifest(store, run="sweeps/20261105T000000Z"))
    write_run(store.root, "sweeps/20261105T000100Z", {**recent, "run": "20261105T000100Z"}, {3: 28})
    write_run(
        store.root,
        "sweeps/20261105T000200Z",
        {**recent, "run": "20261105T000200Z"},
        {5: 2},
        "correlated",
    )
    for path in (store.root / "sweeps/20261105T000200Z").glob("*.parquet"):
        path.rename(store.root / "sweeps/20261105T000100Z" / path.name)
    with pytest.raises(ValueError, match="mixes noise models: correlated, depolarising"):
        resolve(manifest(store, run="sweeps/20261105T000100Z"))


def test_a_run_decoded_with_several_weights_files_is_refused(store: LocalStore) -> None:
    learned(store)
    path = store.root / "evaluations" / "20261031T000100Z" / "run.json"
    record = json.loads(path.read_text())
    record["models"] = {"3": "/scratch/a/decoder.pt", "5": "/scratch/b/decoder.pt"}
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="decoded with 2 weights files"):
        resolve(learned(store))


def test_in_force_names_each_decoder_and_the_chain_behind_it(tmp_path: Path) -> None:
    chain = f"{tmp_path.as_posix()}/chains/20261104T023950Z"
    judged = {
        **FULL_RECORD,
        "run": "20261104T023953Z",
        "noise": "correlated",
        "cells": ["5:0.001", "5:0.005"],
        "parents": [chain + "/", f"{tmp_path.as_posix()}/train/20261104T023952Z"],
    }
    write_run(tmp_path, "evaluations/20261104T023953Z", judged, {5: 12}, "correlated")
    write_run(tmp_path, "sweeps/20261101T172143Z", FULL_RECORD, {3: 28})
    models = tmp_path / "models"
    models.mkdir()
    for noise_model, run in (
        ("correlated", "evaluations/20261104T023953Z"),
        ("depolarising", "sweeps/20261101T172143Z"),
    ):
        fields = {"name": "pymatching", "decoder": "pymatching", "noise_model": noise_model}
        fields |= {"run": f"{tmp_path}/{run}", "image_digest": "sha256:9d217f8c"}
        (models / f"{noise_model}.json").write_text(json.dumps(fields))
    found = in_force(models)
    assert [b.noise_model for b in found] == ["correlated", "depolarising"]
    assert found[0].chain == chain + "/"
    assert found[0].cells == ("5:0.001", "5:0.005")
    assert found[1].chain is None
    text = describe(found)
    assert f"start from: uv run decoder-diagnose {chain}/" in text
    assert "depolarising: pymatching in force from" in text
    assert "stands alone" in text
    assert describe([Baseline("correlated", "pymatching", "x", (), None)]).startswith(
        "correlated: pymatching in force from x"
    )
    with pytest.raises(FileNotFoundError, match="no manifests"):
        in_force(tmp_path / "empty")


def test_a_candidate_is_admissible_unless_worse_or_missing_a_cell() -> None:
    assert admissible(compare(cells({3: 30, 5: 10}), cells({3: 28, 5: 12})))
    assert admissible(compare(cells({3: 300}), cells({3: 100})))
    assert not admissible(compare(cells({3: 100}), cells({3: 300})))
    assert not admissible(compare(cells({3: 30, 5: 10}), cells({3: 30})))


def test_the_command_admits_a_first_manifest_on_its_record(
    tmp_path: Path, store: LocalStore, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_manifest(tmp_path / "m.json", manifest(store))
    assert main([str(path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        f"candidate: {store.uri(FULL)} commit 207f3e5 image sha256:9d217f8c seed 7"
    )
    assert "stands on its own record" in out


def test_the_command_judges_a_candidate_against_the_current(
    tmp_path: Path, store: LocalStore, capsys: pytest.CaptureFixture[str]
) -> None:
    worse = {**FULL_RECORD, "run": "20261031T000000Z", "image_digest": "sha256:new"}
    write_run(store.root, "sweeps/20261031T000000Z", worse, {3: 300, 5: 12, 7: 3})
    current = write_manifest(tmp_path / "current.json", manifest(store))
    candidate = write_manifest(
        tmp_path / "candidate.json",
        manifest(store, run="sweeps/20261031T000000Z", image_digest="sha256:new"),
    )
    assert main([str(candidate), "--against", str(current)]) == 1
    captured = capsys.readouterr()
    assert "3 cells in both runs: 2 within, 0 lower, 1 higher" in captured.out
    assert captured.err.startswith("refused")
    better = {**worse, "run": "20261031T010000Z"}
    write_run(store.root, "sweeps/20261031T010000Z", better, {3: 28, 5: 12, 7: 3})
    candidate = write_manifest(
        tmp_path / "candidate.json",
        manifest(store, run="sweeps/20261031T010000Z", image_digest="sha256:new"),
    )
    assert main([str(candidate), "--against", str(current)]) == 0
    assert "admitted" in capsys.readouterr().out


def test_the_command_reports_a_manifest_that_does_not_resolve(
    tmp_path: Path, store: LocalStore, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_manifest(tmp_path / "m.json", manifest(store, image_digest="sha256:x"))
    assert main([str(path)]) == 2
    assert "the manifest says sha256:x" in capsys.readouterr().err


def test_the_base_directory_matches_manifests_by_noise_model_not_name(
    tmp_path: Path, store: LocalStore, capsys: pytest.CaptureFixture[str]
) -> None:
    base = tmp_path / "base"
    head = tmp_path / "head"
    base.mkdir()
    head.mkdir()
    write_manifest(base / "decoder.json", manifest(store))
    write_manifest(head / "depolarising.json", manifest(store))
    old = {k: v for k, v in manifest(store).__dict__.items() if k != "noise_model"}
    write_manifest(base / "legacy.json", old)
    assert main(["--base", str(base), str(head / "depolarising.json")]) == 0
    out = capsys.readouterr().out
    assert "legacy.json names no noise model" in out
    assert "unchanged from the manifest in force" in out
    worse = {**FULL_RECORD, "run": "20261031T000000Z", "image_digest": "sha256:new"}
    write_run(store.root, "sweeps/20261031T000000Z", worse, {3: 300, 5: 12, 7: 3})
    write_manifest(
        head / "renamed.json",
        manifest(store, run="sweeps/20261031T000000Z", image_digest="sha256:new"),
    )
    (head / "depolarising.json").unlink()
    assert main(["--base", str(base), str(head / "renamed.json")]) == 1
    captured = capsys.readouterr()
    assert "## " in captured.out
    assert "1 higher" in captured.out
    assert captured.err.startswith("refused")


def test_a_decoder_in_force_is_replaced_not_withdrawn(
    tmp_path: Path, store: LocalStore, capsys: pytest.CaptureFixture[str]
) -> None:
    base = tmp_path / "base"
    head = tmp_path / "head"
    base.mkdir()
    head.mkdir()
    write_manifest(base / "depolarising.json", manifest(store))
    write_manifest(head / "correlated.json", learned(store))
    assert main(["--base", str(base), str(head / "correlated.json")]) == 1
    captured = capsys.readouterr()
    assert "stands on its own record" in captured.out
    assert "depolarising has a decoder in force and no candidate" in captured.err


def test_against_takes_one_candidate(tmp_path: Path, store: LocalStore) -> None:
    a = write_manifest(tmp_path / "a.json", manifest(store))
    b = write_manifest(tmp_path / "b.json", manifest(store))
    with pytest.raises(SystemExit):
        main([str(a), str(b), "--against", str(a)])
