"""The decoders in force: one manifest per noise model; ``results-promote`` checks them."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import MISSING, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa

from results.compare import Comparison, compare, provenance, summary
from results.run import RunRecord, read_cells, read_record
from results.store import locate
from sweep.noise import DEPOLARISING

MATCHING = "pymatching"
# Until the decoder loop landed there was one noise model, so a run from before then
# that recorded none was made under it.
CORRELATED_SINCE = datetime(2026, 11, 3, tzinfo=UTC)


@dataclass(frozen=True)
class Manifest:
    """What a file under ``models/`` says: which decoder is in force and what proved it.

    Attributes:
        name: The decoder's name, as the comparison plots label it.
        decoder: How a cell is decoded with it: ``pymatching`` or ``learned``.
        noise_model: The noise model it is in force under; the run must have used it.
        run: The full address of the run that evaluated it.
        image_digest: The digest that run must have recorded; it pins the exact software.
        artifact: The address of the decoder's weights, for a learned decoder.
        artifact_sha256: The hash those weights must have, as hex.
    """

    name: str
    decoder: str
    noise_model: str
    run: str
    image_digest: str
    artifact: str | None = None
    artifact_sha256: str | None = None


@dataclass(frozen=True)
class Baseline:
    """The decoder in force under one noise model, and where to start from to beat it.

    Attributes:
        noise_model: The noise model the manifest is in force under.
        name: The decoder's name.
        run: The full address of the run that earned it.
        cells: The cells that run names, ``distance:rate``, when its record lists them.
        chain: The chain the run came from, by full address; ``None`` for a run that
            stands alone, such as a sweep.
    """

    noise_model: str
    name: str
    run: str
    cells: tuple[str, ...]
    chain: str | None


def read_manifest(path: Path) -> Manifest:
    """Read a manifest file.

    Raises:
        ValueError: When a required field is missing or an unknown one is present.
    """
    raw = json.loads(path.read_text())
    known = {f.name for f in fields(Manifest)}
    required = {f.name for f in fields(Manifest) if f.default is MISSING}
    if missing := required - raw.keys():
        msg = f"{path} lacks {', '.join(sorted(missing))}"
        raise ValueError(msg)
    if unknown := raw.keys() - known:
        msg = f"{path} has fields no manifest has: {', '.join(sorted(unknown))}"
        raise ValueError(msg)
    return Manifest(**raw)


def resolve(manifest: Manifest) -> tuple[RunRecord, pa.Table]:
    """Follow a manifest to its run and that run's cells, checking what it claims.

    Raises:
        ValueError: When the run recorded a different image digest or noise model from
            the manifest's, or when the weights are missing, hash differently or did
            not feed the run.
        FileNotFoundError: When the run, its cells or the weights are not where the
            manifest says.
    """
    store, key = locate(manifest.run)
    record = read_record(store, key)
    if record.image_digest != manifest.image_digest:
        msg = (
            f"{manifest.run} recorded image {record.image_digest or 'none'}, "
            f"the manifest says {manifest.image_digest}"
        )
        raise ValueError(msg)
    cells = read_cells(store, key)
    noise = noise_of(record, cells)
    if noise != manifest.noise_model:
        ran = f"ran under {noise} noise" if noise else "recorded no noise model"
        msg = f"{manifest.run} {ran}, the manifest says {manifest.noise_model}"
        raise ValueError(msg)
    check_weights(manifest, record)
    return record, cells


def noise_of(record: RunRecord, cells: pa.Table) -> str | None:
    """The noise model a run was made under: its cells say, else its record, else its age.

    Cells have carried their noise model since the decoder loop; a run from before
    that recorded none was made under the only model there was. A later run that
    recorded none is ``None``, which no manifest matches.

    Raises:
        ValueError: When the cells disagree among themselves.
    """
    if "noise_model" in cells.column_names:
        found = {str(n) for n in cells.column("noise_model").to_pylist()}
        if len(found) != 1:
            msg = f"{record.key} mixes noise models: {', '.join(sorted(found))}"
            raise ValueError(msg)
        return found.pop()
    noise = json.loads(record.parameters).get("noise")
    if noise is None and record.submitted < CORRELATED_SINCE:
        return DEPOLARISING
    return None if noise is None else str(noise)


def check_weights(manifest: Manifest, record: RunRecord) -> None:
    """Read a learned decoder's weights and hold them to the manifest and the run.

    Matching has no weights, so a matching manifest may not name any. A learned one
    names both the address and the hash; the bytes there must hash as it says, the
    run that holds them must be a parent of the run that was judged, and that run
    must have decoded with one weights file, so the file in force is the one that
    was judged.

    Raises:
        ValueError: On any of those five refusals.
        FileNotFoundError: When there is nothing at the weights' address.
    """
    if manifest.decoder == MATCHING:
        if manifest.artifact or manifest.artifact_sha256:
            msg = f"{manifest.name} is matching and has no weights to name"
            raise ValueError(msg)
        return
    if not (manifest.artifact and manifest.artifact_sha256):
        msg = f"{manifest.name} is learned: name its weights in artifact and artifact_sha256"
        raise ValueError(msg)
    decoded_with = json.loads(record.parameters).get("models", {})
    if len(decoded_with) > 1:
        msg = (
            f"{manifest.run} decoded with {len(decoded_with)} weights files, one per "
            "distance; a manifest names one"
        )
        raise ValueError(msg)
    store, key = locate(manifest.artifact)
    digest = hashlib.sha256(store.read(key)).hexdigest()
    if digest != manifest.artifact_sha256:
        msg = (
            f"{manifest.artifact} hashes to {digest}, the manifest says {manifest.artifact_sha256}"
        )
        raise ValueError(msg)
    source = manifest.artifact.rsplit("/", 1)[0]
    if source not in record.parents:
        msg = f"{manifest.run} was not made from {source}; its parents are {list(record.parents)}"
        raise ValueError(msg)


def admissible(comparison: Comparison) -> bool:
    """Whether a candidate may replace the current decoder.

    It may when it was judged on every cell the current one was and is worse,
    with the intervals apart, on none of them. Being better nowhere is allowed:
    a promotion can be for cost or for speed, as long as it loses no accuracy.
    """
    return comparison.only_a == 0 and comparison.count("higher") == 0


def in_force(models: Path) -> list[Baseline]:
    """The decoder in force under each noise model, from the manifests in a directory.

    Each manifest is followed to its run's record; the first parent under ``chains/``
    is the chain to diagnose.

    Raises:
        FileNotFoundError: When there are no manifests, or a run is not where one says.
        ValueError: When a manifest lacks a field.
    """
    manifests = sorted(models.glob("*.json"))
    if not manifests:
        msg = f"no manifests under {models}"
        raise FileNotFoundError(msg)
    found = []
    for path in manifests:
        manifest = read_manifest(path)
        store, key = locate(manifest.run)
        record = read_record(store, key)
        cells = json.loads(record.parameters).get("cells", [])
        chains = [p for p in record.parents if locate(p)[1].split("/", 1)[0] == "chains"]
        found.append(
            Baseline(
                manifest.noise_model,
                manifest.name,
                manifest.run,
                tuple(cells),
                chains[0] if chains else None,
            )
        )
    return found


def describe(baselines: Sequence[Baseline]) -> str:
    """The baselines as an experiment's State step wants them: one block per noise model."""
    lines = []
    for b in baselines:
        cells = f", cells {' '.join(b.cells)}" if b.cells else ""
        lines.append(f"{b.noise_model}: {b.name} in force from {b.run}{cells}")
        if b.chain:
            lines.append(f"  start from: uv run decoder-diagnose {b.chain}")
        else:
            lines.append("  start from: no chain behind this run; it stands alone")
    return "\n".join(lines)


def by_noise_model(directory: Path) -> dict[str, Path]:
    """The manifests in a directory keyed by noise model; one without the field is skipped.

    The base branch may hold a manifest from before the field existed; it is in
    force under nothing a candidate can be judged against, and is said so.
    """
    found = {}
    for path in sorted(directory.glob("*.json")):
        noise_model = json.loads(path.read_text()).get("noise_model")
        if noise_model is None:
            print(f"{path} names no noise model; nothing is judged against it")
        else:
            found[str(noise_model)] = path
    return found


def judge(candidate: Path, against: Path | None) -> int:
    """Check one candidate manifest, against the one in force when there is one.

    Returns:
        0 when the candidate may be promoted, 1 when the comparison refuses it, 2 when
        a manifest does not resolve.
    """
    if against is not None and candidate.read_bytes() == against.read_bytes():
        print(f"{candidate}: unchanged from the manifest in force")
        return 0
    try:
        resolved, cells = resolve(read_manifest(candidate))
        print(provenance("candidate", resolved))
        if against is None:
            print("no decoder in force; the candidate stands on its own record")
            return 0
        current, current_cells = resolve(read_manifest(against))
        print(provenance("current", current))
    except (ValueError, FileNotFoundError, KeyError) as error:
        print(f"results-promote: {error}", file=sys.stderr)
        return 2
    comparison = compare(current_cells, cells)
    print(summary(comparison))
    if admissible(comparison):
        print("admitted: no cell is worse with the intervals apart")
        return 0
    print("refused: the candidate loses accuracy somewhere, or skipped a cell", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Check candidate manifests against the ones in force.

    Args:
        argv: ``<candidate> [--against <manifest>]`` judges one candidate against one
            manifest; ``--base <directory> <candidate>...`` judges each candidate
            against the manifest in that directory with the same noise model, and
            refuses a noise model the directory has a decoder for and the candidates
            do not, since a decoder is replaced, not withdrawn.

    Returns:
        Exit status: the worst of the candidates' verdicts, 0 admitted, 1 refused,
        2 unresolved.
    """
    parser = argparse.ArgumentParser(
        prog="results-promote", description="admit or refuse decoder manifests"
    )
    parser.add_argument("candidates", nargs="+", type=Path, help="the manifests proposed")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--against", type=Path, help="the manifest in force, if any")
    choice.add_argument("--base", type=Path, help="the directory of the manifests in force")
    args = parser.parse_args(argv)
    if args.base is None:
        if len(args.candidates) > 1:
            parser.error("--against takes one candidate; give --base for several")
        return judge(args.candidates[0], args.against)
    current = by_noise_model(args.base)
    proposed = by_noise_model(Path(args.candidates[0]).parent) if args.candidates else {}
    proposed = {k: v for k, v in proposed.items() if v in args.candidates}
    status = 0
    for noise_model, candidate in proposed.items():
        print(f"## {candidate}")
        status = max(status, judge(candidate, current.get(noise_model)))
    for noise_model in current.keys() - proposed.keys():
        print(
            f"results-promote: {noise_model} has a decoder in force and no candidate; "
            "a decoder is replaced, not withdrawn",
            file=sys.stderr,
        )
        status = max(status, 1)
    return status


if __name__ == "__main__":
    sys.exit(main())
