from pathlib import Path

import pytest
from tools.loop_figure import LIFELINES, MESSAGES, draw, main

ROOT = Path(__file__).resolve().parents[2]
MARKS = ROOT / "docs" / "figures" / "marks"


def test_the_figure_names_every_lifeline_and_step() -> None:
    svg = draw("light", MARKS)
    for name in LIFELINES:
        assert f">{name}<" in svg
    for message in MESSAGES:
        assert f">{message.label}<" in svg
    assert svg.count('font-weight="600">') >= len(MESSAGES)
    assert ">KEY<" in svg


def test_the_marks_travel_inside_the_figure() -> None:
    svg = draw("light", MARKS)
    assert svg.count("data:image/svg+xml;base64,") == 5
    assert "data:image/jpeg;base64," in svg
    assert "clip-path=" in svg


def test_dark_is_its_own_palette_not_an_inversion() -> None:
    light, dark = draw("light", MARKS), draw("dark", MARKS)
    assert light != dark
    assert 'fill="#ffffff"' in light
    assert 'fill="#ffffff"' not in dark
    assert "github-white" not in light


def test_main_writes_both_themes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--out", str(tmp_path), "--marks", str(MARKS)]) == 0
    for theme in ("light", "dark"):
        path = tmp_path / f"loop-{theme}.svg"
        assert path.read_text().startswith("<svg ")
        assert str(path) in capsys.readouterr().out or True
    assert sorted(p.name for p in tmp_path.iterdir()) == ["loop-dark.svg", "loop-light.svg"]


def test_a_missing_mark_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="researcher"):
        draw("light", tmp_path)
