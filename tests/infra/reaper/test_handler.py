from datetime import UTC, datetime, timedelta

from infra.reaper.handler import Instance, instance_from, stale, summary

NOW = datetime(2026, 10, 29, 22, 0, tzinfo=UTC)
MAX_AGE = timedelta(hours=4)


def node(instance_id: str, hours_old: float, cluster: str | None = None) -> Instance:
    return Instance(
        id=instance_id,
        type="c7a.large",
        launched=NOW - timedelta(hours=hours_old),
        cluster=cluster,
    )


def test_stale_picks_instances_older_than_the_limit() -> None:
    old, young = node("i-old", 5), node("i-young", 1)
    assert stale([old, young], NOW, MAX_AGE) == [old]


def test_stale_leaves_cluster_members_to_the_cluster() -> None:
    member = node("i-head", 9, cluster="qec")
    assert stale([member], NOW, MAX_AGE) == []


def test_summary_lists_uptime_and_what_was_terminated() -> None:
    text = summary([node("i-a", 1.5), node("i-b", 5)], [node("i-b", 5)], NOW)
    assert "i-a c7a.large up 1h 30m" in text
    assert "i-b c7a.large up 5h 0m" in text
    assert text.strip().endswith("terminated: i-b")


def test_summary_without_terminations_says_so() -> None:
    assert summary([node("i-a", 1)], [], NOW).strip().endswith("terminated: none")


def test_summary_reports_a_failed_termination() -> None:
    text = summary([node("i-b", 5)], [node("i-b", 5)], NOW, failure="not authorised")
    assert text.strip().endswith("terminate failed (i-b): not authorised")


def test_instance_from_reads_the_cluster_tag() -> None:
    raw = {
        "InstanceId": "i-1",
        "InstanceType": "hpc7a.12xlarge",
        "LaunchTime": NOW,
        "Tags": [{"Key": "parallelcluster:cluster-name", "Value": "qec"}],
    }
    assert instance_from(raw) == Instance("i-1", "hpc7a.12xlarge", NOW, "qec")


def test_instance_from_without_tags() -> None:
    raw = {"InstanceId": "i-2", "InstanceType": "t3.medium", "LaunchTime": NOW}
    assert instance_from(raw).cluster is None
