"""The promoted decoder: a manifest naming the run that earned it; ``results-promote`` checks it."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import MISSING, dataclass, fields
from pathlib import Path

import pyarrow as pa

from results.compare import Comparison, compare, provenance, summary
from results.run import RunRecord, read_cells, read_record
from results.store import locate
from sweep.noise import DEPOLARISING


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


MATCHING = "pymatching"


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
    noise = json.loads(record.parameters).get("noise", DEPOLARISING)
    if noise != manifest.noise_model:
        msg = f"{manifest.run} ran under {noise} noise, the manifest says {manifest.noise_model}"
        raise ValueError(msg)
    check_weights(manifest, record)
    return record, read_cells(store, key)


def check_weights(manifest: Manifest, record: RunRecord) -> None:
    """Read a learned decoder's weights and hold them to the manifest and the run.

    Matching has no weights, so a matching manifest may not name any. A learned one
    names both the address and the hash; the bytes there must hash as it says, and
    the run that holds them must be a parent of the run that was judged, so the
    weights in force are the ones the evaluation decoded with.

    Raises:
        ValueError: On any of those four refusals.
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


def main(argv: Sequence[str] | None = None) -> int:
    """Check a candidate manifest, against the current one when there is one.

    Args:
        argv: ``<candidate manifest> [--against <current manifest>]``.

    Returns:
        Exit status: 0 when the candidate may be promoted, 1 when the comparison
        refuses it, 2 when a manifest does not resolve.
    """
    parser = argparse.ArgumentParser(
        prog="results-promote", description="admit or refuse a decoder manifest"
    )
    parser.add_argument("candidate", type=Path, help="the manifest proposed")
    parser.add_argument("--against", type=Path, help="the manifest in force, if any")
    args = parser.parse_args(argv)
    try:
        candidate, cells = resolve(read_manifest(args.candidate))
        print(provenance("candidate", candidate))
        if args.against is None:
            print("no decoder in force; the candidate stands on its own record")
            return 0
        current, current_cells = resolve(read_manifest(args.against))
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


if __name__ == "__main__":
    sys.exit(main())
