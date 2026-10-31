from io import BytesIO
from pathlib import Path

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from results.store import LocalStore, S3Store, locate, open_store


def test_local_store_lists_keys_under_a_prefix_in_order(store: LocalStore) -> None:
    keys = list(store.keys("sweeps/20261030T001136Z/"))
    assert keys == [
        "sweeps/20261030T001136Z/d3_p0.01_s1000.parquet",
        "sweeps/20261030T001136Z/d5_p0.01_s1000.parquet",
        "sweeps/20261030T001136Z/logs/0.out",
        "sweeps/20261030T001136Z/run.json",
    ]


def test_local_store_writes_and_reads_back(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    store.write("catalogue/runs.parquet", b"bytes")
    assert store.read("catalogue/runs.parquet") == b"bytes"
    assert store.uri("catalogue/runs.parquet") == str(tmp_path / "catalogue/runs.parquet")


def stubbed_s3() -> tuple[S3Store, Stubber]:
    client = boto3.client("s3", region_name="us-east-2")
    return S3Store("bucket", client=client), Stubber(client)


def test_s3_store_walks_every_page_of_the_listing() -> None:
    store, stub = stubbed_s3()
    stub.add_response(
        "list_objects_v2",
        {
            "Contents": [{"Key": "sweeps/a/run.json"}],
            "IsTruncated": True,
            "NextContinuationToken": "t",
        },
        {"Bucket": "bucket", "Prefix": "sweeps/"},
    )
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "sweeps/b/run.json"}], "IsTruncated": False},
        {"Bucket": "bucket", "Prefix": "sweeps/", "ContinuationToken": "t"},
    )
    with stub:
        assert list(store.keys("sweeps/")) == ["sweeps/a/run.json", "sweeps/b/run.json"]


def test_s3_store_reads_and_writes_objects() -> None:
    store, stub = stubbed_s3()
    stub.add_response("put_object", {}, {"Bucket": "bucket", "Key": "k", "Body": b"data"})
    stub.add_response("get_object", {"Body": _body(b"data")}, {"Bucket": "bucket", "Key": "k"})
    with stub:
        store.write("k", b"data")
        assert store.read("k") == b"data"
    assert store.uri("k") == "s3://bucket/k"


def _body(data: bytes) -> StreamingBody:
    return StreamingBody(BytesIO(data), len(data))


def test_open_store_tells_a_bucket_from_a_directory(tmp_path: Path) -> None:
    assert open_store("s3://bucket") == S3Store("bucket")
    assert open_store(str(tmp_path)) == LocalStore(tmp_path)


@pytest.mark.parametrize(
    ("uri", "key"),
    [("s3://bucket/sweeps/x", "sweeps/x"), ("s3://bucket/sweeps/x/", "sweeps/x")],
)
def test_locate_splits_an_s3_address(uri: str, key: str) -> None:
    store, found = locate(uri)
    assert isinstance(store, S3Store)
    assert (store.bucket, found) == ("bucket", key)


def test_locate_reads_a_path_as_a_key_under_the_filesystem_root(tmp_path: Path) -> None:
    store, key = locate(str(tmp_path / "sweeps/x"))
    assert isinstance(store, LocalStore)
    assert store.root / key == (tmp_path / "sweeps/x").resolve()
