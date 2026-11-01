from datetime import timedelta
from pathlib import Path

import pytest

from tests.tools.fakes import (
    BUILT,
    COMMITTED,
    FIRST,
    REPOSITORY,
    SHA,
    SUBMITTED,
    fetch,
    write_run,
)
from tools.loop_plot import Measured, main, measure, plot, summary
from tools.loop_report import Loop

PRICES = {"c7a.large": 0.10, "c8g.large": 0.08}


def price(instance_type: str) -> float:
    return PRICES[instance_type]


def measured(label: str, minutes: float, running: float, billed: float) -> Measured:
    loop = Loop(
        run=label,
        commit=SHA,
        committed=COMMITTED,
        image_built=COMMITTED + timedelta(minutes=1),
        submitted=COMMITTED + timedelta(minutes=2),
        first_cell=COMMITTED + timedelta(minutes=minutes),
    )
    return Measured(label=label, loop=loop, running=running, billed=billed)


def test_measure_joins_the_loop_time_with_the_cost(tmp_path: Path) -> None:
    key = write_run(tmp_path, scaledown_idle_minutes=3)
    got = measure("after", str(tmp_path / key), fetch, price, REPOSITORY)
    assert got.label == "after"
    assert (got.loop.committed, got.loop.image_built) == (COMMITTED, BUILT)
    assert (got.loop.submitted, got.loop.first_cell) == (SUBMITTED, FIRST)
    assert got.running == pytest.approx(4 * 6 / 60 * 0.10)
    assert got.billed == pytest.approx(4 * 9 / 60 * 0.10)


def test_measure_bills_ten_idle_minutes_for_a_run_before_the_tail_was_recorded(
    tmp_path: Path,
) -> None:
    key = write_run(tmp_path)
    got = measure("before", str(tmp_path / key), fetch, price, REPOSITORY)
    assert got.billed == pytest.approx(4 * 16 / 60 * 0.10)


def test_plot_writes_a_png(tmp_path: Path) -> None:
    out = tmp_path / "loop.png"
    plot(measured("before", 13.4, 0.025, 0.30), measured("after", 6.0, 0.02, 0.09), out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_summary_puts_the_two_ratios_in_one_line() -> None:
    text = summary(measured("before", 13.4, 0.025, 0.30), measured("after", 6.7, 0.02, 0.10))
    assert text == (
        "loop 12.4 min -> 5.7 min (0.46x) with 1.0 min -> 1.0 min of waiting, "
        "billed $0.300 -> $0.100 (0.33x)"
    )


def test_main_measures_both_runs_and_draws_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = write_run(tmp_path, run="20261031T002000Z")
    after = write_run(tmp_path, run="20261031T003000Z", scaledown_idle_minutes=3)
    out = tmp_path / "loop.png"
    argv = [
        "--before", str(tmp_path / before), "--after", str(tmp_path / after),
        "--repository", REPOSITORY, "--out", str(out),
    ]  # fmt: skip
    assert main(argv, fetch=fetch, price=price) == 0
    assert out.exists()
    assert capsys.readouterr().out.strip().endswith(f"-> {out}")


def test_main_makes_the_directory_the_figure_goes_in(tmp_path: Path) -> None:
    before = write_run(tmp_path, run="20261031T002000Z")
    after = write_run(tmp_path, run="20261031T003000Z", scaledown_idle_minutes=3)
    out = tmp_path / "plots" / "loop.png"
    argv = ["--before", str(tmp_path / before), "--after", str(tmp_path / after)]
    assert (
        main([*argv, "--repository", REPOSITORY, "--out", str(out)], fetch=fetch, price=price) == 0
    )
    assert out.exists()
