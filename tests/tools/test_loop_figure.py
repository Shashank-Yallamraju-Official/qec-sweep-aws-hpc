import shutil
from pathlib import Path

import pytest

from tools.loop_figure import LIFELINES, MESSAGES, Message, draw, embed, main

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


def test_main_writes_both_themes_and_says_where(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--out", str(tmp_path), "--marks", str(MARKS)]) == 0
    printed = capsys.readouterr().out
    for theme in ("light", "dark"):
        path = tmp_path / f"loop-{theme}.svg"
        assert path.read_text().startswith("<svg ")
        assert str(path) in printed
    assert sorted(p.name for p in tmp_path.iterdir()) == ["loop-dark.svg", "loop-light.svg"]


def test_a_mark_missing_for_one_theme_writes_neither(tmp_path: Path) -> None:
    marks = tmp_path / "marks"
    shutil.copytree(MARKS, marks)
    (marks / "github-white.svg").unlink()
    out = tmp_path / "out"
    assert main(["--out", str(out), "--marks", str(marks)]) == 2
    assert not out.exists() or not list(out.iterdir())


def test_a_message_is_one_of_three_kinds() -> None:
    assert {m.kind for m in MESSAGES} == {"request", "reply", "result"}
    with pytest.raises(ValueError, match="kind"):
        Message(0, 1, "x", kind="wish")  # type: ignore[arg-type]


def test_a_mark_of_an_unknown_type_is_refused(tmp_path: Path) -> None:
    odd = tmp_path / "researcher.gif"
    odd.write_bytes(b"GIF89a")
    with pytest.raises(ValueError, match="gif"):
        embed(odd)


def test_a_missing_mark_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="researcher"):
        draw("light", tmp_path)
