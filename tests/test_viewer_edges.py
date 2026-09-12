"""Real-browser regression tests for the shared rendered outputs and static UI."""

import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lecture.export_static import export_static
from lecture.ir import LectureManifest
from lecture.trace import TraceExecutor

pytestmark = pytest.mark.skipif(
    os.environ.get("LECTPY_BROWSER_TESTS") != "1", reason="opt-in Chromium test"
)


@pytest.fixture
def viewer(tmp_path):
    from playwright.sync_api import sync_playwright

    out = tmp_path / "bundle"
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(out))
    )
    base = f"http://127.0.0.1:{httpd.server_port}"
    source = tmp_path / "edges.py"
    source.write_text(
        "from lecture import text, hide, equation, code, whiteboard, browser_open, browser_close\n"
        "@hide\n"
        "def intro():\n"
        '    text("# Framework edge checks")\n'
        '    equation(r"123.45 + .25 = 123.70 \\qquad \\left\\{x\\right\\}")\n'
        '    code("x = 1\\n\\nx += 1", "python", output_id="blank-line")\n'
        '    whiteboard("Grid", background="grid", insertable=True)\n'
        '    whiteboard("Dots", background="dots", insertable=True)\n'
        f'    browser_open("{base}/lecture.json", window_id="ref")\n'
        "@hide\n"
        "def close_reference():\n"
        '    browser_close("ref")\n'
        "@hide\n"
        "def reopen_reference():\n"
        f'    browser_open("{base}/lecture.json", window_id="ref")\n'
        "def main():\n"
        "    intro()  # @hide\n"
        "    close_reference()\n"
        "    reopen_reference()\n"
        "    return\n",
        encoding="utf-8",
    )
    export_static(
        TraceExecutor().trace_file(source),
        LectureManifest(title="Framework edge checks", view="presenter"),
        out,
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(base)
            yield page
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_manual_reference_open_immediately_enables_close(viewer):
    with viewer.expect_popup() as popup:
        viewer.get_by_role("button", name="Open reference window", exact=True).click()
    assert viewer.get_by_role("button", name="Close reference window", exact=True).is_enabled()
    viewer.get_by_role("button", name="Close reference window", exact=True).click()
    assert popup.value.is_closed()


def test_historical_close_does_not_close_a_later_open_on_render(viewer):
    with viewer.expect_popup() as first:
        viewer.get_by_role("button", name="Open reference window", exact=True).click()
    viewer.locator("#stage").press("ArrowRight")
    assert first.value.is_closed()
    with viewer.expect_popup() as reopened:
        viewer.locator("#stage").press("ArrowRight")
    assert not reopened.value.is_closed()
    viewer.get_by_role("combobox", name="Output highlight", exact=True).select_option("violet")
    assert not reopened.value.is_closed()


def test_blank_code_lines_can_be_targeted_and_highlighted(viewer):
    assert viewer.locator('[data-code-line="2"]').is_visible()


def test_two_whiteboard_snapshots_keep_distinct_patterns_and_keyboard_scope(viewer):
    for title in ("Grid", "Dots"):
        viewer.get_by_role("button", name=f"Open {title}", exact=True).click()
        board = viewer.get_by_role("region", name=title, exact=True)
        board.get_by_role("button", name="Insert snapshot", exact=True).click()
        before = viewer.url
        board.locator(".wb-input").press("ArrowRight")
        assert viewer.url == before
        board.get_by_role("button", name="Close whiteboard", exact=True).click()
    ids = viewer.locator(".wb-commit pattern").evaluate_all("nodes => nodes.map(n => n.id)")
    assert len(set(ids)) == 2
    assert viewer.locator("math mn").all_text_contents() == ["123.45", ".25", "123.70"]
