"""Opt-in integration against real Chromium: LECTPY_BROWSER_TESTS=1 pytest this file."""

import asyncio
import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from lecture.broker.automation import AutomationService
from lecture.broker.automation_http import automation_handler
from lecture.export_static import export_static
from lecture.ir import LectureManifest, sha256_file
from lecture.trace import TraceExecutor

pytestmark = pytest.mark.skipif(
    os.environ.get("LECTPY_BROWSER_TESTS") != "1", reason="opt-in Chromium test"
)


def test_popup_board_rendered_code_stop_capture_and_rewind(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples" / "playwright_controls.py"
    ctx = TraceExecutor().trace_file(source)
    out = export_static(
        ctx,
        LectureManifest(
            source_file=str(source), source_sha256=sha256_file(source), view="presenter"
        ),
        tmp_path / "bundle",
    )
    bundle = json.loads((out / "lecture.json").read_text())
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(out))
    )
    base = f"http://127.0.0.1:{httpd.server_port}"
    service = AutomationService(source, bundle, base, headless=True)
    httpd.RequestHandlerClass = automation_handler(out, service)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def run(id, action, step=0):
        service.submit(id, action, uuid4().hex, step)
        target = "lecture" if service.specs[id]["target"] == "lecture" else id
        service.active[target].result(timeout=35)
        state = service.snapshot()["controls"][id]
        if state["state"] != "succeeded" and service.presenter:
            print(inspect(service.presenter.locator("body").inner_text()))
        assert state["state"] == "succeeded", state["message"]
        return state

    def inspect(coro):
        return asyncio.run_coroutine_threadsafe(coro, service.loop).result(timeout=15)

    try:
        with pytest.raises(HTTPError) as denied:
            urlopen(Request(base + "/_lecture/automation", data=b"{}", method="POST"))
        assert denied.value.code == 403
        with urlopen(base + "/_lecture/automation") as response:
            token = json.load(response)["token"]
        # Exercise the real HTTP command path, not only direct service submission.
        command = {"id": "experiment", "action": "experiment.load", "request_id": uuid4().hex}
        with urlopen(
            Request(
                base + "/_lecture/automation",
                data=json.dumps(command).encode(),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
        ) as response:
            assert response.status == 202
        service.active["experiment"].result(timeout=35)
        assert service.snapshot()["controls"]["experiment"]["state"] == "succeeded"
        popup = service.pages["experiment"]
        assert inspect(popup.opener()) is service.presenter
        run("experiment", "experiment.step")
        assert "iteration 2" in run("experiment", "experiment.step")["message"]
        captures = run("experiment", "$capture")["captures"]
        with urlopen(base + f"/_lecture/automation/captures/{captures[-1]['id']}.png") as response:
            assert response.read(8) == b"\x89PNG\r\n\x1a\n"

        run("working", "board.work", 1)
        assert inspect(service.presenter.locator(".wb-commit").count()) == 1
        assert inspect(
            service.presenter.get_by_role("button", name="Open Working", exact=True).is_visible()
        )
        run("script", "code.gradient", 2)
        assert (
            inspect(service.presenter.locator('[data-code-line="3"]').get_attribute("aria-current"))
            == "true"
        )
        run("script", "code.update", 2)
        assert (
            inspect(service.presenter.locator('[data-code-line="4"]').get_attribute("aria-current"))
            == "true"
        )
        assert (
            inspect(service.presenter.locator('[data-code-line="3"]').get_attribute("aria-current"))
            is None
        )
        assert "iteration 2" in inspect(popup.get_by_label("Experiment state").inner_text())

        # Rewinding reprojects the board without repeating its action or losing its snapshot.
        run("working", "$open", 1)
        assert inspect(service.presenter.locator(".wb-commit").count()) == 1
        assert "iteration 2" in inspect(popup.get_by_label("Experiment state").inner_text())
        # Screenshots of actual managed pages are optional local QA artifacts.
        if folder := os.environ.get("LECTPY_BROWSER_ARTIFACTS"):
            dest = Path(folder).resolve()
            dest.mkdir(parents=True, exist_ok=True)
            inspect(service.presenter.screenshot(path=str(dest / "whiteboard.png"), full_page=True))
            inspect(popup.screenshot(path=str(dest / "popup.png")))
            run("script", "code.update", 2)
            inspect(service.presenter.screenshot(path=str(dest / "script.png"), full_page=True))

        service.submit("experiment", "experiment.wait", "waiting", 3)
        service.submit("experiment", "$stop", "stop", 3)
        inspect(asyncio.sleep(0.05))
        assert service.snapshot()["controls"]["experiment"]["state"] == "cancelled"
        assert "iteration 3" in run("experiment", "experiment.step", 3)["message"]
        run("experiment", "$close", 3)
        assert popup.is_closed()
        inspect(service.presenter.locator("#stage").press("ArrowLeft"))
        assert "experiment" not in service.pages  # no popup resurrection on rewind
    finally:
        service.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def test_automatic_popup_lifecycle_never_reopens_on_rewind(tmp_path):
    source = tmp_path / "lifecycle.py"
    source.write_text(
        "from lecture import clear, hide, section, text\n"
        "from lecture.browser import PlaywrightControls\n"
        'popup = PlaywrightControls("auto", on_enter="open", on_leave="close")\n'
        "@hide\n"
        "def intro():\n"
        '    text("Introduction")\n'
        "@hide\n"
        "def demo():\n"
        "    clear()\n"
        '    with section("Demo", controls=(popup,)):\n'
        '        text("Automatic popup")\n'
        "@hide\n"
        "def end():\n"
        "    clear()\n"
        '    text("Finished")\n'
        "def main():\n"
        "    intro()  # @hide\n"
        "    demo()\n"
        "    end()\n"
        "    return\n",
        encoding="utf-8",
    )
    ctx = TraceExecutor().trace_file(source)
    out = export_static(
        ctx,
        LectureManifest(source_sha256=sha256_file(source), view="presenter"),
        tmp_path / "bundle",
    )
    bundle = json.loads((out / "lecture.json").read_text())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SimpleHTTPRequestHandler)
    service = AutomationService(
        source, bundle, f"http://127.0.0.1:{httpd.server_port}", headless=True
    )
    httpd.RequestHandlerClass = automation_handler(out, service)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def inspect(coro):
        return asyncio.run_coroutine_threadsafe(coro, service.loop).result(timeout=15)

    def until(predicate):
        deadline = monotonic() + 10
        while not predicate():
            assert monotonic() < deadline, service.snapshot()
            sleep(0.02)

    try:
        presenter = inspect(service._presenter(0))
        assert service.pages == {}  # initial load is inert
        inspect(presenter.locator("#stage").press("ArrowRight"))
        until(lambda: service.snapshot()["controls"]["auto"]["message"] == "Popup open")
        popup = service.pages["auto"]
        inspect(presenter.locator("#stage").press("ArrowRight"))
        until(lambda: service.snapshot()["controls"]["auto"]["message"] == "Window closed")
        assert popup.is_closed()
        request_count = len(service.requests)
        inspect(presenter.locator("#stage").press("ArrowLeft"))
        inspect(asyncio.sleep(0.1))
        assert service.pages == {}
        assert len(service.requests) == request_count
        inspect(presenter.reload())
        assert service.pages == {}  # loading directly into the section is also inert
    finally:
        service.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)
