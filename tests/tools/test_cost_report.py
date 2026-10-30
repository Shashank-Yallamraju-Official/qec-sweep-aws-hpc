import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools.cost_report import (
    Run,
    billed_node_hours,
    cost,
    main,
    only,
    read_run,
    report,
    running_node_hours,
)

RUN = Run(
    run="20261030T001136Z",
    queue="sweep",
    instance_type="c7a.large",
    nodes=4,
    submitted=datetime(2026, 10, 30, 0, 11, 36, tzinfo=UTC),
    finished=datetime(2026, 10, 30, 0, 21, 36, tzinfo=UTC),
)


def record(**fields: object) -> dict[str, object]:
    base: dict[str, object] = {
        "run": "r",
        "queue": "sweep",
        "nodes": 4,
        "instance_type": "c7a.large",
        "submitted": "2026-10-30T00:11:36Z",
        "finished": "2026-10-30T00:21:36Z",
    }
    return {**base, **fields}


def test_running_node_hours_cover_submission_to_finish() -> None:
    assert running_node_hours(RUN) == pytest.approx(4 * 10 / 60)


def test_billed_node_hours_add_the_idle_tail_before_scale_down() -> None:
    assert billed_node_hours(RUN, idle=timedelta(minutes=10)) == pytest.approx(4 * 20 / 60)


def test_cost_is_node_hours_at_the_rate() -> None:
    assert cost(4 * 20 / 60, price_per_hour=0.1) == pytest.approx(4 * 20 / 60 * 0.1)


def test_read_run_prefers_the_nodes_the_run_actually_used(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(record(queue="sweep-spot", nodes=None, nodes_used=16)))
    run = read_run(path)
    assert run.nodes == 16
    assert run.queue == "sweep-spot"
    assert run.finished - run.submitted == timedelta(minutes=10)


def test_read_run_refuses_a_record_with_no_node_count(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(record(nodes=None)))
    with pytest.raises(ValueError, match="node count"):
        read_run(path)


def test_report_separates_running_cost_from_the_idle_tail() -> None:
    text = report(RUN, on_demand=0.10, spot=0.03)
    assert "4 x c7a.large for 10.0 min: 0.67 node-hours running, 1.33 billed" in text
    assert "on demand: $0.067 running, $0.133 billed at $0.1000/h" in text
    assert "spot: $0.020 running, $0.040 billed at $0.0300/h" in text


def test_only_names_what_is_missing() -> None:
    assert only([7], "a price") == 7
    with pytest.raises(ValueError, match="no a price; pass it on the command line"):
        only([], "a price")


def test_main_takes_a_zero_rate_as_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "run.json"
    path.write_text(json.dumps(record()))
    assert main([str(path), "--on-demand", "0.10", "--spot", "0"]) == 0
    assert "spot: $0.000 running" in capsys.readouterr().out
