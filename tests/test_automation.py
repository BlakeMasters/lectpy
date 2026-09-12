import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from lecture import code, section, text
from lecture.broker.automation import AutomationService
from lecture.browser import PlaywrightControls, browser_script
from lecture.context import execution_scope
from lecture.export_static import export_static
from lecture.ir import LectureManifest
from lecture.trace import TraceExecutor


@browser_script("test.noop")
async def noop(page):
    raise AssertionError("must not execute during build")


def test_control_declarations_are_immutable_serializable_and_scoped():
    actions = {"Run": noop}
    control = PlaywrightControls("browser", actions=actions)
    actions.clear()
    with execution_scope() as ctx:
        with section("Same label", controls=(control,)):
            outer = text("outer")
            with section("Same label", controls=(PlaywrightControls("child"),)):
                inner = text("inner")
            restored = text("restored")
        unscoped = text("outside")
        with section("Same label", controls=(control,)):
            repeated = text("repeated")
    assert len(control.actions) == 1
    assert len(inner.payload["control_ids"]) == 2
    assert outer.payload["control_ids"] == restored.payload["control_ids"]
    assert repeated.payload["control_ids"] != outer.payload["control_ids"]
    assert "control_ids" not in unscoped.payload
    json.dumps(ctx.log.to_list())
    with pytest.raises(TypeError):
        control.actions["Changed"] = noop


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "bad id"},
        {"target": "random-tab"},
        {"viewport": (True, 500)},
        {"viewport": (9000, 700)},
        {"url": "file:///secret"},
        {"timeout": float("nan")},
        {"on_enter": "run-everything"},
        {"target": "lecture", "on_leave": "close"},
        {"actions": {"Run": lambda p: None}},
    ],
)
def test_invalid_options(kwargs):
    with pytest.raises((TypeError, ValueError)):
        PlaywrightControls(**{"id": "test", **kwargs})


def example_bundle():
    source = Path(__file__).resolve().parents[1] / "examples" / "playwright_controls.py"
    ctx = TraceExecutor().trace_file(source)
    assert not any(e.kind == "error" for e in ctx.log.subscribe())
    return (
        source,
        ctx,
        {
            "manifest": {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
            "events": ctx.log.to_list(),
        },
    )


def test_example_builds_without_running_scripts_and_static_engine_is_optional(tmp_path):
    source, ctx, _ = example_bundle()
    assert sum(e.kind == "step" for e in ctx.log.subscribe()) == 4
    out = export_static(ctx, LectureManifest(source_file=str(source)), tmp_path / "lab")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "export class AutomationClient" in html
    with execution_scope() as plain:
        code("x = 1", output_id="source")
    out = export_static(plain, LectureManifest(), tmp_path / "plain")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "export class AutomationClient" not in html
    assert 'data-code-line=\\"1\\"' in html


def test_source_fingerprint_and_registered_actions():
    source, _, bundle = example_bundle()
    with pytest.raises(ValueError, match="source changed"):
        AutomationService(source, {**bundle, "manifest": {}}, "http://127.0.0.1:9000")
    service = AutomationService(source, bundle, "http://127.0.0.1:9000")
    try:
        with pytest.raises(ValueError, match="not declared"):
            service.submit("experiment", "arbitrary.python", "request")
        with pytest.raises(ValueError, match="step"):
            service.submit("experiment", "$open", "request", 999)
        assert service.browser is None
    finally:
        service.close()


def test_duplicate_requests_busy_stop_and_timeout():
    source, _, bundle = example_bundle()
    service = AutomationService(source, bundle, "http://127.0.0.1:9000")
    calls = []

    async def fake_perform(id, action, step):
        calls.append(action)
        if action == "experiment.wait":
            await asyncio.sleep(10)
        if action == "experiment.load":
            await asyncio.sleep(0.2)
        service._state(id, "succeeded", "done")

    service._perform = fake_perform
    try:
        service.submit("experiment", "experiment.step", "first")
        service.active["experiment"].result(timeout=2)
        assert service.submit("experiment", "experiment.step", "first")["duplicate"]
        assert calls == ["experiment.step"]
        with pytest.raises(ValueError, match="another command"):
            service.submit("experiment", "$open", "first")
        service.submit("experiment", "experiment.wait", "wait")
        with pytest.raises(ValueError, match="busy"):
            service.submit("experiment", "$open", "busy")
        service.submit("experiment", "$stop", "stop")
        # Drain cancellation on the worker loop.
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.05), service.loop).result(timeout=2)
        assert service.snapshot()["controls"]["experiment"]["state"] == "cancelled"
        service.submit("experiment", "experiment.wait", "wait-before-replacement")
        service.submit("experiment", "$stop", "stop-before-replacement")
        service.submit("experiment", "experiment.load", "replacement")
        asyncio.run_coroutine_threadsafe(asyncio.sleep(0.05), service.loop).result(timeout=2)
        assert service.snapshot()["controls"]["experiment"]["state"] == "running"
        service.active["experiment"].result(timeout=2)
        service.submit("experiment", "experiment.wait", "wait-before-close")
        service.submit("experiment", "$close", "close-while-running")
        service.active["experiment"].result(timeout=2)
        assert service.snapshot()["controls"]["experiment"]["state"] == "succeeded"
        assert calls[-1] == "$close"
        service.specs["experiment"]["timeout"] = 0.01
        service.submit("experiment", "experiment.wait", "timeout")
        service.active["experiment"].result(timeout=2)
        assert service.snapshot()["controls"]["experiment"]["state"] == "error"
    finally:
        service.close()
