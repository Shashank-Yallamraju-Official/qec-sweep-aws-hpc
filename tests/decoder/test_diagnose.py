import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from decoder.diagnose import CONVERGED, OVERFIT, UNDERFIT, diagnose, main, report
from sweep.cell import Cell
from sweep.decode import CellResult
from sweep.noise import Noise, noisy_circuit
from sweep.parquet import write

NOISE: Noise = "correlated"
TRAINED_AT = 0.05
RATES = (0.02, TRAINED_AT)
ERRORS = {0.02: (4, 9), TRAINED_AT: (20, 30)}  # matching, learned
SHOTS = 200


def training_record(losses: list[float], accuracy: float, held_out: float) -> dict[str, object]:
    return {
        "cell": {"distance": 3, "noise": TRAINED_AT, "shots": 50_000},
        "samples": ["d3_p0.05_s50000_seed0_correlated.npz"],
        "shots": 50_000,
        "held_out": 5_000,
        "seed": 0,
        "epochs": len(losses),
        "learning_rate": 0.001,
        "batch": 256,
        "ranks": 1,
        "epoch_losses": losses,
        "loss": losses[-1],
        "accuracy": accuracy,
        "held_out_loss": 0.1,
        "held_out_accuracy": held_out,
        "device": "cpu",
        "seconds": 9.0,
        "torch": "2.15.0+cpu",
    }


def write_chain(root: Path, training: dict[str, object]) -> Path:
    train = root / "train" / "20261103T000001Z"
    train.mkdir(parents=True)
    (train / "run.json").write_text(
        json.dumps({"run": train.name, "queue": "sweep", "submitted": "2026-11-03T00:00:01Z"})
    )
    (train / "train.json").write_text(json.dumps(training))
    evaluations = {}
    for decoder, name in (("pymatching", "20261103T000002Z"), ("learned", "20261103T000003Z")):
        run = root / "evaluations" / name
        run.mkdir(parents=True)
        run.joinpath("run.json").write_text(
            json.dumps({"run": name, "queue": "sweep", "submitted": "2026-11-03T00:00:02Z"})
        )
        for rate, counts in ERRORS.items():
            result = CellResult(
                cell=Cell(3, rate, SHOTS),
                errors=counts[0] if decoder == "pymatching" else counts[1],
                seconds=1.0,
                seed=0,
                started=datetime(2026, 11, 3, tzinfo=UTC),
                host="node",
                decoder=decoder,
                noise_model=NOISE,
            )
            write(result, run)
        evaluations[decoder] = str(run)
    chain = root / "chains" / "20261103T000000Z"
    chain.mkdir(parents=True)
    (chain / "run.json").write_text(
        json.dumps(
            {
                "run": chain.name,
                "queue": "sweep",
                "submitted": "2026-11-03T00:00:00Z",
                "noise": NOISE,
                "seed": 0,
                "cells": [f"3:{TRAINED_AT}"],
                "rates": [str(r) for r in RATES],
                "children": {"train": [str(train)], "evaluations": evaluations},
            }
        )
    )
    return chain


@pytest.fixture
def improving_chain(tmp_path: Path) -> Path:
    return write_chain(tmp_path, training_record([0.5, 0.3, 0.2, 0.15], 0.94, 0.938))


def test_every_evaluated_cell_gets_floor_matching_and_learned(improving_chain: Path) -> None:
    diagnosis = diagnose(str(improving_chain))
    cells = {state.cell.noise: state for state in diagnosis.cells}
    assert set(cells) == set(RATES)
    at = cells[TRAINED_AT]
    assert (at.matching.errors, at.learned.errors) == ERRORS[TRAINED_AT]
    assert at.ratio == pytest.approx(30 / 20)
    sampler = noisy_circuit(Cell(3, TRAINED_AT, SHOTS), NOISE).compile_detector_sampler(seed=0)
    _, observables = sampler.sample(SHOTS, separate_observables=True)
    assert at.floor == pytest.approx(observables[:, 0].mean())


def test_a_cell_is_in_distribution_only_at_a_rate_the_model_trained_on(
    improving_chain: Path,
) -> None:
    cells = {state.cell.noise: state for state in diagnose(str(improving_chain)).cells}
    assert cells[TRAINED_AT].in_distribution is True
    assert cells[0.02].in_distribution is False


def test_a_falling_loss_with_no_held_out_gap_is_underfit(improving_chain: Path) -> None:
    (training,) = diagnose(str(improving_chain)).trainings
    assert training.last_epoch_drop == pytest.approx(0.25)
    assert training.still_improving is True
    assert training.fit == UNDERFIT


def test_a_flat_loss_with_a_held_out_gap_is_overfit(tmp_path: Path) -> None:
    chain = write_chain(tmp_path, training_record([0.3, 0.1, 0.1, 0.1], 0.99, 0.90))
    (training,) = diagnose(str(chain)).trainings
    assert training.still_improving is False
    assert training.fit == OVERFIT


def test_a_flat_loss_with_no_gap_has_converged(tmp_path: Path) -> None:
    chain = write_chain(tmp_path, training_record([0.3, 0.1, 0.1, 0.1], 0.95, 0.949))
    (training,) = diagnose(str(chain)).trainings
    assert training.fit == CONVERGED


def test_report_is_markdown_naming_what_it_read(improving_chain: Path) -> None:
    diagnosis = diagnose(str(improving_chain))
    text = report(diagnosis)
    assert "| cell |" in text
    assert "underfit" in text
    assert "off" in text  # the cell at 0.02 is off-distribution
    assert str(improving_chain) in text


def test_main_prints_the_report(improving_chain: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(improving_chain)]) == 0
    assert "| cell |" in capsys.readouterr().out
