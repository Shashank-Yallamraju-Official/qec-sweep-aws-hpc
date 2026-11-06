import json
from pathlib import Path

import pytest

from tests.decoder.test_diagnose import ERRORS, RATES, training_record, write_chain
from tools.learning_curve import Curve, Point, draw, main, read_chain


def chain(root: Path, seed: int = 0, noise: str | None = None) -> Path:
    path = write_chain(root, training_record([0.5, 0.3, 0.2], 0.94, 0.938), seed=seed)
    record = json.loads((path / "run.json").read_text())
    record["seed"] = seed
    if noise:
        record["noise"] = noise
    (path / "run.json").write_text(json.dumps(record))
    return path


def test_a_chain_becomes_one_point_per_cell_at_its_training_shots(tmp_path: Path) -> None:
    curve = read_chain(str(chain(tmp_path)))
    assert curve.noise == "correlated"
    assert curve.seed == 0
    by_rate = {p.rate: p for p in curve.points}
    assert set(by_rate) == set(RATES)
    for rate, (matching, learned) in ERRORS.items():
        point = by_rate[rate]
        assert point.shots == 50_000
        assert point.ratio == pytest.approx(learned / matching)
        assert point.low < point.ratio < point.high
    assert str(tmp_path / "chains") in curve.read[0]


def test_the_figure_names_what_it_read_and_labels_each_rate(tmp_path: Path) -> None:
    svg = draw("light", [read_chain(str(chain(tmp_path)))])
    assert svg.startswith("<svg ")
    assert "<desc>Read: " in svg
    assert str(tmp_path / "chains" / "20261103T000000Z") in svg
    for rate in RATES:
        assert f"p = {rate:g} · " in svg
    assert ">matching<" in svg
    assert ">training shots<" in svg


def test_a_later_seed_is_hollow_on_the_same_hue(tmp_path: Path) -> None:
    first = read_chain(str(chain(tmp_path / "a", seed=0)))
    second = read_chain(str(chain(tmp_path / "b", seed=100)))
    one = draw("light", [first])
    two = draw("light", [first, second])
    assert one.count("<circle") < two.count("<circle")
    assert "seed 100, nudged right" in two
    assert "nudged" not in one
    assert two.count('<path d="') == one.count('<path d="')


def test_dark_is_its_own_palette_not_an_inversion(tmp_path: Path) -> None:
    curves = [read_chain(str(chain(tmp_path)))]
    light, dark = draw("light", curves), draw("dark", curves)
    assert light != dark
    assert 'fill="#ffffff"' in light
    assert 'fill="#ffffff"' not in dark
    assert "#2a78d6" in light
    assert "#2a78d6" not in dark


def test_two_noise_models_are_refused(tmp_path: Path) -> None:
    curves = [
        read_chain(str(chain(tmp_path / "a"))),
        read_chain(str(chain(tmp_path / "b", seed=1, noise="depolarising"))),
    ]
    with pytest.raises(ValueError, match="one noise model"):
        draw("light", curves)


def test_more_rates_than_hues_are_refused() -> None:
    points = tuple(Point(10, rate, 1.0, 0.9, 1.1) for rate in (0.001, 0.002, 0.003, 0.004))
    with pytest.raises(ValueError, match="hues"):
        draw("light", [Curve("correlated", 0, points, ())])


def test_main_writes_both_themes_and_says_where(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    assert main([str(chain(tmp_path)), "--out", str(out), "--name", "curve"]) == 0
    printed = capsys.readouterr().out
    for theme in ("light", "dark"):
        path = out / f"curve-{theme}.svg"
        assert path.read_text().startswith("<svg ")
        assert str(path) in printed


def test_main_refuses_a_mixed_figure_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = chain(tmp_path / "a")
    b = chain(tmp_path / "b", seed=1, noise="depolarising")
    out = tmp_path / "out"
    assert main([str(a), str(b), "--out", str(out)]) == 2
    assert "one noise model" in capsys.readouterr().err
    assert not out.exists()
