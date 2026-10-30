import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tools.cost_report import Run, billed_node_hours, cost, main, read_run, report

RUN = Run(
    run="20261030T001136Z",
    queue="sweep",
    instance_type="c7a.large",
    nodes=4,
    submitted=datetime(2026, 10, 30, 0, 11, 36, tzinfo=UTC),
    finished=datetime(2026, 10, 30, 0, 21, 36, tzinfo=UTC),
)


def test_billed_node_hours_include_the_idle_tail_before_scale_down() -> None:
    assert billed_node_hours(RUN, idle=timedelta(minutes=10)) == pytest.approx(4 * 20 / 60)


def test_cost_is_node_hours_at_the_rate() -> None:
    assert cost(RUN, price_per_hour=0.1) == pytest.approx(4 * 20 / 60 * 0.1)


def test_read_run_prefers_the_nodes_the_queue_had_up(tmp_path: Path) -> None:
    path = tmp_path / "run.json"
    path.write_text(
        json.dumps(
            {
                "run": "r",
                "queue": "sweep-spot",
                "nodes": None,
                "nodes_up": 16,
                "instance_type": "c7a.large",
                "submitted": "2026-10-30T00:11:36Z",
                "finished": "2026-10-30T00:21:36Z",
            }
        )
    )
    run = read_run(path)
    assert run.nodes == 16
    assert run.queue == "sweep-spot"
    assert run.finished - run.submitted == timedelta(minutes=10)


def test_report_prices_on_demand_and_spot_side_by_side() -> None:
    text = report(RUN, on_demand=0.10, spot=0.03)
    assert "4 x c7a.large for 10.0 min, billed 1.33 node-hours" in text
    assert "on demand: $0.133" in text
    assert "spot: $0.040" in text


def test_main_takes_prices_on_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "run.json"
    path.write_text(
        json.dumps(
            {
                "run": "r",
                "queue": "sweep",
                "nodes": 4,
                "instance_type": "c7a.large",
                "submitted": "2026-10-30T00:11:36Z",
                "finished": "2026-10-30T00:21:36Z",
            }
        )
    )
    assert main([str(path), "--on-demand", "0.10", "--spot", "0.03"]) == 0
    assert "spot: $0.040" in capsys.readouterr().out
