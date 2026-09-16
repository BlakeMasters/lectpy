"""Opt-in Chromium checks for playback in the static viewer and built React shell."""

import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from lecture import equation, step_keyables, step_playback, text, uml, whiteboard
from lecture.context import ExecutionContext, execution_scope
from lecture.export_static import export_static
from lecture.ir import LectureManifest

pytestmark = pytest.mark.skipif(
    os.environ.get("LECTPY_BROWSER_TESTS") != "1", reason="opt-in Chromium test"
)


@pytest.fixture(params=["static", "react"])
def playback_viewer(request, tmp_path):
    from playwright.sync_api import sync_playwright

    app = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if request.param == "react" and not (app / "index.html").is_file():
        pytest.skip("Build the React shell with npm run build first")
    bundle = tmp_path / "bundle"

    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            path = urlsplit(path).path
            root = bundle if path.startswith("/bundle/") else app
            self.directory = str(root)
            return super().translate_path(path.removeprefix("/bundle"))

        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def open_viewer(*, view="presenter", reduced=False, restart=False, leave=True):
                ctx = ExecutionContext()
                trajectory = {
                    "series": [{"points": [(-2 + i / 20, -1 + i / 40) for i in range(41)]}]
                }
                responses = [{
                    "title": f"Panel {i}", "series": [{"values": [j / 40 for j in range(41)]}]
                } for i in range(3)]
                with execution_scope(ctx):
                    # These modules previously collided with the playback module's helpers.
                    equation("x^2")
                    uml("class", {"classes": [{"name": "State"}]})
                    whiteboard("Working")
                    with step_keyables({"ArrowDown": "step.next"}):
                        step_playback(
                            trajectory, responses, title="Primary", output_id="primary",
                            autoplay_on_step=True, restart_on_enter=restart, pause_on_leave=leave,
                            keyables={
                                "ArrowUp": "playback.play", "ArrowDown": "playback.pause",
                                "Space": "playback.toggle", "Shift+ArrowRight": "step.next",
                            },
                        )
                        step_playback(trajectory, responses, title="Secondary")
                        ctx.emit("step", {"line": 1})
                    # Malformed recorded metadata must not break ordinary navigation.
                    ctx.emit("step", {"line": 2, "step_keyables": [None, {}, {
                        "key": "ArrowRight", "action": "unknown.action",
                    }]})
                    text("Final teaching step")
                    ctx.emit("step", {"line": 3})
                export_static(ctx, LectureManifest(title="Playback review", view=view), bundle)
                page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
                base = f"http://127.0.0.1:{httpd.server_port}"
                path = "/bundle/" if request.param == "static" else "/?bundle=/bundle/lecture.json"
                page.goto(base + path)
                page.get_by_role("region", name="Primary", exact=True).wait_for()
                assert not errors
                return page

            yield open_viewer
            assert not errors
            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def position(page, index=0):
    return float(page.get_by_role("slider", name="Playback position").nth(index).input_value())


def wait_for_progress(page, previous=0, index=0):
    page.wait_for_function(
        "([index, previous]) => "
        "Number(document.querySelectorAll('.step-playback-range input')[index].value) > previous",
        arg=[index, previous],
    )


def test_play_pause_scope_precedence_and_navigation_preserve_progress(playback_viewer):
    page = playback_viewer()
    wait_for_progress(page)
    stage = page.locator("#stage")
    stage.press("ArrowDown")
    paused = position(page)
    stage.press("Control+ArrowRight")
    assert "step=1" not in page.url  # Unbound modified arrows retain browser behavior.
    url = page.url
    page.wait_for_timeout(150)
    assert position(page) == paused
    assert page.url == url  # The output's Down binding wins over the trace scope's next.
    stage.press("ArrowUp")
    wait_for_progress(page, paused)
    stage.press("ArrowDown")
    paused = position(page)
    page.get_by_role("combobox", name="Output highlight", exact=True).select_option("violet")
    assert position(page) == paused  # Display changes must not remount/restart playback.
    stage.press("Shift+ArrowRight")
    assert "step=1" in page.url
    assert position(page) == paused
    stage.press("ArrowLeft")
    wait_for_progress(page, paused)  # Reenter without restart resumes from the same frame.
    stage.press("ArrowDown")
    stage.press("ArrowRight")
    stage.press("ArrowRight")  # Invalid key metadata on the middle step is ignored.
    assert "step=2" in page.url


def test_pause_on_leave_and_restart_on_enter(playback_viewer):
    page = playback_viewer(restart=True)
    slider = page.get_by_role("slider", name="Playback position").first
    slider.fill("30")
    stage = page.locator("#stage")
    stage.press("ArrowRight")
    assert position(page) == 30
    stage.press("ArrowLeft")
    stage.press("ArrowDown")
    assert position(page) < 5
    stage.press("ArrowUp")
    wait_for_progress(page)
    stage.press("ArrowRight")
    paused = position(page)
    page.wait_for_timeout(150)
    assert position(page) == paused


def test_playback_can_continue_after_leaving_when_configured(playback_viewer):
    page = playback_viewer(leave=False)
    wait_for_progress(page)
    page.locator("#stage").press("ArrowRight")
    wait_for_progress(page, position(page))


def test_reduced_motion_advances_discrete_frames(playback_viewer):
    page = playback_viewer(reduced=True)
    wait_for_progress(page)
    page.locator("#stage").press("ArrowDown")
    assert position(page).is_integer()
    assert position(page) >= 1


def test_reader_waits_for_play_and_targets_the_focused_figure(playback_viewer):
    page = playback_viewer(view="reader")
    page.wait_for_timeout(150)
    assert position(page) == position(page, 1) == 0
    secondary = page.get_by_role("region", name="Secondary", exact=True)
    button = secondary.get_by_role("button")
    button.press("ArrowUp")
    wait_for_progress(page, index=1)
    button.press("ArrowDown")
    assert position(page) == 0
    paused = position(page, 1)
    button.press("Space")  # Native Space activates this button once, without global routing.
    wait_for_progress(page, paused, index=1)
    button.press("ArrowDown")


def test_negative_trajectory_and_three_response_panels_fit_the_svg(playback_viewer):
    page = playback_viewer()
    page.locator("#stage").press("ArrowDown")
    assert page.get_by_role("button", name="Open Working", exact=True).is_visible()
    assert page.locator(".lecture-uml svg").is_visible()
    assert page.locator("math").is_visible()
    assert page.locator(".step-playback-svg-wrap").first.evaluate("""wrap => {
        const frame = wrap.querySelector('[data-chart-frame]');
        const marker = wrap.querySelector('.step-playback-current-marker');
        const x = Number(marker.getAttribute('cx')), y = Number(marker.getAttribute('cy'));
        return x >= Number(frame.getAttribute('x')) && y >= Number(frame.getAttribute('y'))
          && x <= Number(frame.getAttribute('x')) + Number(frame.getAttribute('width'))
          && y <= Number(frame.getAttribute('y')) + Number(frame.getAttribute('height'));
    }""")
    assert page.locator(".step-playback-svg-wrap").nth(1).evaluate("""wrap => {
        const svg = wrap.querySelector('svg');
        return [...svg.querySelectorAll('[data-chart-frame]')].every(frame =>
          Number(frame.getAttribute('y')) + Number(frame.getAttribute('height'))
            < svg.viewBox.baseVal.height);
    }""")


def test_native_buttons_keep_space_and_sliders_keep_arrow_keys(playback_viewer):
    page = playback_viewer()
    page.locator("#stage").press("ArrowDown")
    paused = position(page)
    page.get_by_role("button", name="Open Working", exact=True).press("Space")
    page.get_by_role("button", name="Close whiteboard", exact=True).wait_for()
    page.wait_for_timeout(150)
    assert position(page) == paused
    slider = page.get_by_role("slider", name="Playback position").first
    url = page.url
    slider.press("ArrowRight")
    assert position(page) > paused
    assert page.url == url
