"""Where runs live: a bucket or a directory, addressed by key the way S3 is."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

S3_SCHEME = "s3://"


class Store(Protocol):
    """A flat namespace of keys under one root."""

    def uri(self, key: str) -> str:
        """The full address of a key, the form a record uses to name another run."""

    def keys(self, prefix: str = "") -> Iterator[str]:
        """Every key under a prefix, in sorted order."""

    def read(self, key: str) -> bytes:
        """The bytes at a key."""

    def write(self, key: str, data: bytes) -> None:
        """Put bytes at a key, replacing what was there."""


@dataclass(frozen=True)
class LocalStore:
    """A directory standing in for a bucket, for tests and for runs copied down."""

    root: Path

    def uri(self, key: str) -> str:
        """The file's path."""
        return str(self.root / key)

    def keys(self, prefix: str = "") -> Iterator[str]:
        """Every file under the prefix, as keys relative to the root."""
        base = self.root / prefix
        walk = base if base.is_dir() else base.parent
        for path in sorted(p for p in walk.rglob("*") if p.is_file()):
            key = path.relative_to(self.root).as_posix()
            if key.startswith(prefix):
                yield key

    def read(self, key: str) -> bytes:
        """The file's bytes."""
        return (self.root / key).read_bytes()

    def write(self, key: str, data: bytes) -> None:
        """Write the file, making its directory."""
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


@cache
def s3_client() -> S3Client:
    """The one S3 client every store shares; building one loads credentials and models."""
    return boto3.client("s3")


@dataclass(frozen=True)
class S3Store:
    """One bucket."""

    bucket: str
    client: S3Client = field(default_factory=s3_client, repr=False, compare=False)

    def uri(self, key: str) -> str:
        """The object's ``s3://`` address."""
        return f"{S3_SCHEME}{self.bucket}/{key}"

    def keys(self, prefix: str = "") -> Iterator[str]:
        """Every object key under the prefix, which S3 lists in order."""
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefix
        )
        for key in pages.search("Contents[].Key"):
            if key is not None:
                yield str(key)

    def read(self, key: str) -> bytes:
        """The object's bytes.

        Raises:
            FileNotFoundError: When there is no such object, as a directory would.
        """
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.NoSuchKey as error:
            raise FileNotFoundError(self.uri(key)) from error
        with response["Body"] as body:
            return bytes(body.read())

    def write(self, key: str, data: bytes) -> None:
        """Put the object; a locked bucket keeps the version it replaces."""
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)


def open_store(uri: str) -> Store:
    """The store a root names: ``s3://bucket`` or a directory.

    Raises:
        ValueError: For a key after the bucket; a store is a whole bucket.
    """
    if uri.startswith(S3_SCHEME):
        bucket, _, key = uri.removeprefix(S3_SCHEME).partition("/")
        if key:
            msg = f"a store is a whole bucket; {uri} names a key in one"
            raise ValueError(msg)
        return S3Store(bucket)
    return LocalStore(Path(uri))


def locate(uri: str) -> tuple[Store, str]:
    """Split a run's full address into its store and its key within it.

    ``s3://bucket/sweeps/x`` is the key ``sweeps/x`` in that bucket. A directory
    is read the same way, as ``<kind>/<run>`` under the store two levels up.
    """
    if uri.startswith(S3_SCHEME):
        bucket, _, key = uri.removeprefix(S3_SCHEME).partition("/")
        return S3Store(bucket), key.rstrip("/")
    path = Path(uri).resolve()
    return LocalStore(path.parents[1]), f"{path.parent.name}/{path.name}"
