from pathlib import Path

import numpy as np
import pytest

from decoder.sample import Samples, layout, main, read, sample, write
from sweep.cell import Cell
from sweep.noise import memory_circuit

CELL = Cell(distance=3, noise=0.01, shots=50)


def test_layout_gives_every_detector_one_place_in_a_round_by_stabiliser_grid() -> None:
    circuit = memory_circuit(CELL)
    grid = layout(circuit)
    assert grid.rounds == 4
    assert grid.stabilisers == 8
    assert sorted(grid.slots) == list(range(circuit.num_detectors))
    assert len(set(zip(grid.rounds_of, grid.stabilisers_of, strict=True))) == circuit.num_detectors


def test_sample_arranges_detection_events_by_round_and_keeps_the_observable() -> None:
    samples = sample(CELL, seed=3)
    assert samples.detectors.shape == (50, 4, 8)
    assert samples.detectors.dtype == np.uint8
    assert samples.flips.shape == (50,)
    assert samples.flips.dtype == np.uint8
    events, observables = (
        memory_circuit(CELL).compile_detector_sampler(seed=3).sample(50, separate_observables=True)
    )
    assert samples.detectors.sum() == events.sum()
    assert np.array_equal(samples.flips, observables[:, 0].astype(np.uint8))


def test_the_same_seed_gives_the_same_samples() -> None:
    assert np.array_equal(sample(CELL, seed=1).detectors, sample(CELL, seed=1).detectors)
    assert not np.array_equal(sample(CELL, seed=1).detectors, sample(CELL, seed=2).detectors)


def test_correlated_noise_turns_the_per_round_data_noise_into_y_errors() -> None:
    plain = str(memory_circuit(CELL))
    correlated = str(sample(CELL, seed=0, noise="correlated").circuit)
    assert "DEPOLARIZE1" in plain
    assert "DEPOLARIZE1" not in correlated
    assert correlated.count("Y_ERROR") == plain.count("DEPOLARIZE1")
    assert correlated.count("DEPOLARIZE2") == plain.count("DEPOLARIZE2")


def test_samples_are_named_by_cell_seed_and_noise_and_read_back(tmp_path: Path) -> None:
    samples = sample(CELL, seed=7, noise="correlated")
    path = write(samples, tmp_path)
    assert path == tmp_path / "d3_p0.01_s50_seed7_correlated.npz"
    back = read(path)
    assert back.cell == CELL
    assert (back.seed, back.noise) == (7, "correlated")
    assert np.array_equal(back.detectors, samples.detectors)
    assert np.array_equal(back.flips, samples.flips)


def test_main_writes_one_file_and_names_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--d", "3", "--p", "0.01", "--shots", "20", "--seed", "0", "--out", str(tmp_path)]
    assert main(argv) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "d3_p0.01_s20_seed0_depolarising.npz")
    assert isinstance(read(tmp_path / "d3_p0.01_s20_seed0_depolarising.npz"), Samples)


def test_main_refuses_an_unknown_noise_model(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            ["--d", "3", "--p", "0.01", "--shots", "2", "--noise", "biased", "--out", str(tmp_path)]
        )
