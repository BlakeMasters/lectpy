"""Optional browser-control declarations. Importing this module never starts Playwright."""

from __future__ import annotations

import inspect
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Literal
from urllib.parse import urlsplit


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise ValueError("browser id must contain 1–80 letters, numbers, '.', '_' or '-'")
    return value


def browser_script(id: str):
    """Register a module-level async function, invoked only by a local runner."""
    _identifier(id)

    def decorate(function: Callable) -> Callable:
        if not inspect.iscoroutinefunction(function) or "<locals>" in function.__qualname__:
            raise TypeError("browser scripts must be module-level async functions")
        function.__lecture_browser_script__ = id
        return function

    return decorate


@dataclass(frozen=True)
class PlaywrightControls:
    id: str
    actions: Mapping[str, Callable] = field(default_factory=dict)
    target: Literal["popup", "lecture"] = "popup"
    url: str = "about:blank"
    viewport: tuple[int, int] = (1000, 700)
    on_enter: Literal["manual", "open"] = "manual"
    on_leave: Literal["keep", "close"] = "keep"
    timeout: float = 15

    def __post_init__(self) -> None:
        _identifier(self.id)
        if self.target not in ("popup", "lecture"):
            raise ValueError("browser target must be popup or lecture")
        if not isinstance(self.url, str) or len(self.url) > 4096:
            raise ValueError("browser url must be a string of at most 4096 characters")
        if self.url != "about:blank" and urlsplit(self.url).scheme not in ("http", "https"):
            raise ValueError("browser url must use http(s) or about:blank")
        if (
            not isinstance(self.viewport, tuple)
            or len(self.viewport) != 2
            or any(
                type(v) is not int or not lo <= v <= hi
                for v, lo, hi in zip(self.viewport, (320, 180), (3840, 2160), strict=True)
            )
        ):
            raise ValueError("viewport must be a (width, height) tuple within 320×180–3840×2160")
        if self.on_enter not in ("manual", "open") or self.on_leave not in ("keep", "close"):
            raise ValueError("use on_enter=manual/open and on_leave=keep/close")
        if self.target == "lecture" and self.on_leave == "close":
            raise ValueError(
                "the controlled lecture must be closed explicitly, not on section exit"
            )
        if (
            type(self.timeout) not in (int, float)
            or not math.isfinite(self.timeout)
            or not 0 < self.timeout <= 120
        ):
            raise ValueError("browser timeout must be between 0 and 120 seconds")
        if not isinstance(self.actions, Mapping) or len(self.actions) > 16:
            raise ValueError("actions must be a mapping of at most 16 labels to browser scripts")
        actions = dict(self.actions)
        for label, function in actions.items():
            if not isinstance(label, str) or not label.strip() or len(label) > 80:
                raise ValueError(
                    "browser action labels must be non-empty and at most 80 characters"
                )
            if not getattr(function, "__lecture_browser_script__", None):
                raise TypeError("actions must reference @browser_script functions")
        object.__setattr__(self, "actions", MappingProxyType(actions))

    def with_options(self, **overrides: Any) -> PlaywrightControls:
        return replace(self, **overrides)

    def to_props(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "url": self.url,
            "viewport": list(self.viewport),
            "timeout": self.timeout,
            "on_enter": self.on_enter,
            "on_leave": self.on_leave,
            "actions": [
                {"label": label, "script": fn.__lecture_browser_script__}
                for label, fn in self.actions.items()
            ],
        }


async def highlight_code(page, output_id: str, line: int) -> None:
    """Highlight one rendered code line until the output is rendered again."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", output_id):
        raise ValueError("invalid code output_id")
    if type(line) is not int or line < 1:
        raise ValueError("line is one-based")
    code = page.locator(f'[data-output-id="{output_id}"]')
    target = code.locator(f'[data-code-line="{line}"]')
    await target.wait_for(state="visible")
    await code.locator("[data-code-line]").evaluate_all(
        "nodes => nodes.forEach(node => node.removeAttribute('aria-current'))"
    )
    await target.evaluate("node => node.setAttribute('aria-current', 'true')")
    await target.scroll_into_view_if_needed()
