import json

import pytest

from lecture import browser_close, browser_open
from lecture.context import ExecutionContext, execution_scope
from lecture.export_static import export_static
from lecture.ir import LectureManifest


def test_browser_reference_emits_legacy_component_descriptor(tmp_path):
    ctx = ExecutionContext()
    with execution_scope(ctx):
        opened = browser_open(
            "https://arxiv.org/",
            window_id="papers",
            title="arXiv papers",
            width=1024,
            height=768,
            left=80,
            top=40,
            resizable=False,
            focus=False,
        )
        closed = browser_close("papers")
    assert opened.kind == closed.kind == "component"
    assert opened.payload["component_type"] == "browser-window"
    assert opened.payload["props"] == {
        "action": "open",
        "window_id": "papers",
        "url": "https://arxiv.org/",
        "title": "arXiv papers",
        "width": 1024,
        "height": 768,
        "left": 80,
        "top": 40,
        "resizable": False,
        "focus": False,
    }
    assert opened.payload["permissions"] == {"network": ["arxiv.org"]}
    assert closed.payload["props"] == {"action": "close", "window_id": "papers"}

    out = export_static(ctx, LectureManifest(title="Reference"), tmp_path / "out")
    bundle = json.loads((out / "lecture.json").read_text(encoding="utf-8"))
    html = (out / "index.html").read_text(encoding="utf-8")
    assert [item["payload"]["props"]["action"] for item in bundle["events"]] == ["open", "close"]
    assert "BrowserWindowController" in html
    assert '<script type="module">' in html
    assert "Open reference window" in html
    assert "width=1024" not in html  # geometry is data, not executable feature markup


@pytest.mark.parametrize(
    "call, message",
    [
        (lambda: browser_open("javascript:alert(1)"), "http"),
        (lambda: browser_open("/relative/reference"), "http"),
        (lambda: browser_open("https://example.test/", width=319), "width"),
        (lambda: browser_open("https://example.test/", height=2161), "height"),
        (lambda: browser_open("https://example.test/", left=-10001), "left"),
        (lambda: browser_open("https://example.test/", window_id="bad id"), "window_id"),
        (lambda: browser_open("https://example.test/", resizable=1), "bool"),
        (lambda: browser_close("bad id"), "window_id"),
    ],
)
def test_browser_reference_rejects_unsafe_or_unbounded_options(call, message):
    with execution_scope(ExecutionContext()), pytest.raises((ValueError, TypeError), match=message):
        call()


def test_browser_close_can_be_recorded_before_any_open(tmp_path):
    ctx = ExecutionContext()
    with execution_scope(ctx):
        browser_close()
    out = export_static(ctx, LectureManifest(title="Close"), tmp_path / "out")
    assert "Close request recorded" in (out / "index.html").read_text(encoding="utf-8")
