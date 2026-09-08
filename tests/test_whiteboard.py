import json

import pytest

from lecture import text, whiteboard
from lecture.context import ExecutionContext, execution_scope
from lecture.export_static import export_static
from lecture.ir import LectureManifest


def test_whiteboard_uses_existing_component_protocol(tmp_path):
    ctx = ExecutionContext()
    with execution_scope(ctx):
        event = whiteboard("Derivation", width=1000, height=700, background="dots")
    assert event.kind == "component"
    assert event.payload["component_type"] == "whiteboard"
    assert event.payload["props"] == {
        "title": "Derivation",
        "width": 1000,
        "height": 700,
        "background": "dots",
    }
    out = export_static(ctx, LectureManifest(title="Board"), tmp_path / "out")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert '<script type="module">' in html
    assert "export function mountWhiteboard" in html
    assert "getCoalescedEvents" in html
    assert html.count("</script>") == 2
    assert json.loads((out / "lecture.json").read_text())["events"][0]["kind"] == "component"


def test_plain_exports_do_not_include_drawing_engine(tmp_path):
    ctx = ExecutionContext()
    with execution_scope(ctx):
        text("A small document")
    out = export_static(ctx, LectureManifest(), tmp_path / "out")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "export function mountWhiteboard" not in html
    assert "getCoalescedEvents" not in html


@pytest.mark.parametrize(
    "kwargs",
    [{"width": True}, {"width": 1}, {"height": 9999}, {"background": "invalid"}, {"title": 123}],
)
def test_whiteboard_rejects_bad_configuration(kwargs):
    with execution_scope(ExecutionContext()), pytest.raises((ValueError, TypeError)):
        whiteboard(**kwargs)
