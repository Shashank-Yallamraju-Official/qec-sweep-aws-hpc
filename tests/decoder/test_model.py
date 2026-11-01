from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from decoder.model import RecurrentDecoder, build, load, save  # noqa: E402
from decoder.sample import sample  # noqa: E402
from sweep.cell import Cell  # noqa: E402

CELL = Cell(distance=3, noise=0.01, shots=5)


def test_build_sizes_the_input_to_the_code_stabilisers() -> None:
    model = build(CELL, hidden=16)
    assert isinstance(model, RecurrentDecoder)
    assert model.stabilisers == 8
    assert model.hidden == 16


def test_forward_gives_one_logit_per_shot() -> None:
    model = build(CELL, hidden=16)
    samples = sample(CELL, seed=0)
    logits = model(torch.from_numpy(samples.detectors))
    assert logits.shape == (5,)
    assert torch.isfinite(logits).all()


def test_predict_turns_logits_into_flips() -> None:
    model = build(CELL, hidden=16)
    flips = model.predict(torch.from_numpy(sample(CELL, seed=0).detectors))
    assert flips.shape == (5,)
    assert flips.dtype == torch.uint8
    assert set(flips.tolist()) <= {0, 1}


def test_save_and_load_round_trip_the_model(tmp_path: Path) -> None:
    model = build(CELL, hidden=16, layers=1)
    detectors = torch.from_numpy(sample(CELL, seed=0).detectors)
    path = save(model, tmp_path / "decoder.pt")
    back = load(path)
    assert (back.stabilisers, back.hidden, back.layers) == (8, 16, 1)
    assert torch.equal(back(detectors), model(detectors))
