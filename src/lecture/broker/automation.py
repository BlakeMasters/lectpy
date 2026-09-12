"""Opt-in local Playwright service, independent of the HTTP transport and viewers."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4


class AutomationService:
    def __init__(self, source: Path, bundle: dict, base_url: str, *, headless: bool = False):
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.execution_id = next((e["execution_id"] for e in bundle["events"]), "")
        self.step_count = sum(e["kind"] == "step" for e in bundle["events"])
        self.specs = {}
        for event in bundle["events"]:
            payload = event.get("payload", {})
            if payload.get("component_type") == "playwright-controls":
                props = payload["props"]
                prior = self.specs.get(props["id"])
                # Lifecycle options may vary by section; a target/action identity may not.
                keys = ("id", "target", "url", "viewport", "actions", "timeout")
                if prior and any(prior[k] != props[k] for k in keys):
                    raise ValueError(f"conflicting declarations for browser control {props['id']}")
                self.specs[props["id"]] = props
        if not self.specs:
            raise ValueError("bundle has no Playwright controls")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != bundle["manifest"].get("source_sha256"):
            raise ValueError(
                "script source changed: rebuild the lecture before serving with --scripts"
            )
        module_name = f"_lecture_browser_{uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, source)
        if spec is None or spec.loader is None:
            raise ValueError("cannot load browser scripts")
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = self.module
        try:
            spec.loader.exec_module(self.module)
            self.scripts = {}
            for value in vars(self.module).values():
                script_id = getattr(value, "__lecture_browser_script__", None)
                if script_id:
                    if script_id in self.scripts and self.scripts[script_id] is not value:
                        raise ValueError(f"duplicate browser script id: {script_id}")
                    self.scripts[script_id] = value
            for control in self.specs.values():
                for action in control["actions"]:
                    if action["script"] not in self.scripts:
                        raise ValueError(f"script is not registered: {action['script']}")
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        self.lock = threading.RLock()
        self.states = {
            key: {"state": "idle", "message": "Ready", "captures": []} for key in self.specs
        }
        self.requests = OrderedDict()
        self.images = {}
        self.active = {}
        self.tasks = set()
        self.pages = {}
        self.presenter = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page_lock = None
        self.target_locks = {}
        self.capture_serial = 0
        # Playwright objects stay on one asyncio thread. HTTP stays responsive while awaiting.
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(
                json.dumps({"execution_id": self.execution_id, "controls": self.states})
            )

    def _state(self, id: str, state: str, message: str) -> None:
        with self.lock:
            self.states[id].update(state=state, message=message[:1000])

    def submit(self, id: str, action: str, request_id: str, step: int = 0) -> dict:
        if id not in self.specs:
            raise ValueError("unknown browser control")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("request_id is required (at most 100 characters)")
        if type(step) is not int or not 0 <= step < max(1, self.step_count):
            raise ValueError("invalid lecture step")
        spec = self.specs[id]
        actions = {a["script"] for a in spec["actions"]}
        if action not in {"$open", "$close", "$capture", "$stop", *actions}:
            raise ValueError("action is not declared by this control")
        identity = (id, action, step)
        target = "lecture" if spec["target"] == "lecture" else id
        with self.lock:
            if request_id in self.requests:
                if self.requests[request_id] != identity:
                    raise ValueError("request_id was already used for another command")
                return {"accepted": True, "duplicate": True}
            current = self.active.get(target)
            if current and not current.done():
                if action not in {"$stop", "$close"}:
                    raise ValueError(
                        "target is busy; stop the current action before starting another"
                    )
                current.cancel()
            self.requests[request_id] = identity
            while len(self.requests) > 256:
                self.requests.popitem(last=False)
            if action == "$stop":
                return {"accepted": True}
            self._state(id, "running", "Opening browser…" if action == "$open" else "Running…")
            future = asyncio.run_coroutine_threadsafe(self._execute(id, action, step), self.loop)
            self.active[target] = future

            def completed(result):
                with self.lock:
                    if result.cancelled() and self.active.get(target) is result:
                        self._state(
                            id, "cancelled", "Stopped. Completed browser actions were not undone."
                        )

            future.add_done_callback(completed)
        return {"accepted": True}

    async def _ensure_browser(self):
        if self.browser and self.browser.is_connected():
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Install lectpy[playwright], then run python -m playwright install chromium"
            ) from exc
        if self.playwright is None:
            self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(viewport={"width": 1200, "height": 850})
        self.pages.clear()
        self.presenter = None

    async def _presenter(self, step: int, *, synchronize: bool = True):
        await self._ensure_browser()
        if self.presenter is None or self.presenter.is_closed():
            self.presenter = await self.context.new_page()
            await self.presenter.goto(f"{self.base_url}/?view=presenter&step={step}")
        elif synchronize:
            current = int(parse_qs(urlsplit(self.presenter.url).query).get("step", ["0"])[0])
            # Use the viewer's navigation to preserve local whiteboard state, not a reload.
            for _ in range(abs(step - current)):
                await self.presenter.locator("#stage").press(
                    "ArrowRight" if step > current else "ArrowLeft"
                )
        return self.presenter

    async def _page(self, spec: dict, step: int):
        presenter = await self._presenter(step, synchronize=spec["target"] == "lecture")
        if spec["target"] == "lecture":
            return presenter
        page = self.pages.get(spec["id"])
        if page is not None and not page.is_closed():
            return page
        width, height = spec["viewport"]
        async with presenter.expect_popup() as pending:
            await presenter.evaluate(
                "s => window.open(s.url, s.name, s.features)",
                {
                    "url": spec["url"],
                    "name": f"lectpy_automation_{spec['id']}",
                    "features": f"popup=yes,width={width},height={height}",
                },
            )
        page = await pending.value
        await page.set_viewport_size({"width": width, "height": height})
        self.pages[spec["id"]] = page
        return page

    async def _execute(self, id: str, action: str, step: int):
        task = asyncio.current_task()
        self.tasks.add(task)
        spec = self.specs[id]
        target = "lecture" if spec["target"] == "lecture" else id
        lock = self.target_locks.setdefault(target, asyncio.Lock())
        try:
            async with lock:
                await asyncio.wait_for(self._perform(id, action, step), timeout=spec["timeout"])
        except asyncio.CancelledError:
            # The future callback updates cancellation only while this request is
            # still current. An older cancellation must not overwrite a new run.
            raise
        except asyncio.TimeoutError:
            self._state(
                id, "error", "Action timed out. The browser is left as-is; retry or close it."
            )
        except Exception as exc:
            self._state(id, "error", str(exc))
        finally:
            self.tasks.discard(task)

    async def _perform(self, id: str, action: str, step: int):
        spec = self.specs[id]
        if action == "$close":
            page = self.presenter if spec["target"] == "lecture" else self.pages.pop(id, None)
            if page and not page.is_closed():
                await page.close()
            self._state(id, "succeeded", "Window closed")
            return
        if self.page_lock is None:
            self.page_lock = asyncio.Lock()
        async with self.page_lock:
            page = await self._page(spec, step)
        page.set_default_timeout(spec["timeout"] * 800)
        if action == "$open":
            await page.bring_to_front()
            self._state(
                id,
                "succeeded",
                "Controlled lecture open" if spec["target"] == "lecture" else "Popup open",
            )
        elif action == "$capture":
            data = await page.screenshot(type="png", animations="disabled")
            if len(data) > 8 * 1024 * 1024:
                raise ValueError("screenshot exceeds 8 MB; use a smaller viewport")
            key = uuid4().hex
            with self.lock:
                self.capture_serial += 1
                self.images[key] = data
                captures = self.states[id]["captures"]
                captures.append({"id": key, "caption": f"{id} — capture {self.capture_serial}"})
                if len(captures) > 3:
                    self.images.pop(captures.pop(0)["id"], None)
            self._state(id, "succeeded", "Screenshot inserted below the controls")
        else:
            result = await self.scripts[action](page)
            self._state(id, "succeeded", str(result) if result is not None else "Action complete")

    async def _shutdown(self):
        # Never cancel Playwright's transport task before closing its browsers.
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def close(self):
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self.loop).result(timeout=8)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=2)
            if not self.thread.is_alive():
                self.loop.close()
            sys.modules.pop(self.module.__name__, None)
