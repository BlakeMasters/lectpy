from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from lecture import PresentationStyle, WhiteboardOptions, section, text, whiteboard
from lecture.context import ExecutionContext, execution_scope
from lecture.export_static import export_static
from lecture.ir import LectureManifest
from lecture.styles import PAPER, TECHNICAL
from lecture.trace import TraceExecutor


def test_styles_are_validated_immutable_copies():
    custom = TECHNICAL.with_options(highlight="violet")
    assert custom.highlight == "violet"
    assert TECHNICAL.highlight == "amber"
    with pytest.raises(FrozenInstanceError):
        custom.font = "reading"
    with pytest.raises(ValueError, match="font"):
        PresentationStyle(font="comic-sans")
    with pytest.raises(TypeError):
        custom.with_options(typo="wide")


def test_nested_sections_inherit_override_and_restore_on_exception():
    ctx = ExecutionContext()
    with execution_scope(ctx):
        with section("Outer", style=TECHNICAL):
            with pytest.raises(RuntimeError), section("Inner", highlight="violet"):
                inner = text("inner")
                raise RuntimeError("author error")
            outer = text("outer")
            with section("Paper", style=PAPER, density="roomy"):
                paper = text("paper")
        unscoped = text("unscoped")
    assert inner.payload["presentation"] == {
        "name": "Inner",
        **TECHNICAL.with_options(highlight="violet").to_dict(),
    }
    assert outer.payload["presentation"] == {"name": "Outer", **TECHNICAL.to_dict()}
    assert paper.payload["presentation"] == {
        "name": "Paper",
        **PAPER.with_options(density="roomy").to_dict(),
    }
    assert "presentation" not in unscoped.payload


def test_whiteboard_options_allow_explicit_false_and_preserve_preset():
    options = WhiteboardOptions(insertable=True, close_on_insert=True, color="#7c3aed")
    with execution_scope():
        event = whiteboard(options=options, close_on_insert=False, stroke_width=8)
    assert event.payload["props"]["color"] == "#7c3aed"
    assert event.payload["props"]["stroke_width"] == 8
    assert "close_on_insert" not in event.payload["props"]
    assert options.close_on_insert is True
    assert options.stroke_width == 4


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stroke_width": True},
        {"stroke_width": 49},
        {"color": "blue"},
        {"tool": "spray"},
        {"close_on_insert": True},
        {"insertable": "yes"},
    ],
)
def test_invalid_board_options(kwargs):
    with pytest.raises((ValueError, TypeError)):
        WhiteboardOptions(**kwargs)


def test_example_has_six_complete_scenes_and_shared_static_styles(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples" / "presentation_options.py"
    ctx = TraceExecutor().trace_file(source)
    events = ctx.log.subscribe()
    assert not any(e.kind == "error" for e in events)
    steps = [e for e in events if e.kind == "step"]
    assert len(steps) == 6
    # A debugger pauses before a line: no empty opening or skipped final scene.
    for index, step in enumerate(steps):
        end = float("inf") if index == 5 else step.seq
        clear_seq = max(e.seq for e in events if e.kind == "clear" and e.seq <= end)
        headings = [
            e
            for e in events
            if clear_seq < e.seq <= end
            and e.kind == "text"
            and e.payload.get("markdown", "").startswith("# ")
        ]
        assert len(headings) == 1
        assert headings[0].payload["presentation"]["name"].startswith(f"0{index + 1} /")
    out = export_static(ctx, LectureManifest(title="Options"), tmp_path / "bundle")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "function sectionPresentation(event)" in html
    assert ".section-font-reading" in html
    assert "body[data-view=reader]" in html
