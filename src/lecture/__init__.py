"""Author-facing SDK — plain Python executable lectures.

Level A needs no frontend code. Every primitive emits a typed event on the
scoped ExecutionContext (ContextVar), so concurrent sessions never share the
legacy process-global `_current_renderings` accumulator.
"""

from __future__ import annotations

import functools
import inspect as pyinspect
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .context import require_current
from .events import Event, SourceLocation
from .sanitize import markdown_to_html

__all__ = [
    "text",
    "code",
    "table",
    "note",
    "image",
    "asset",
    "video",
    "link",
    "plot",
    "inspect_value",
    "clear",
    "system_text",
    "component",
    "section",
    "whiteboard",
    "browser_open",
    "browser_close",
    "terminal",
    "inspect",
    "hide",
    "step_over",
]


def _caller_location() -> SourceLocation | None:
    """Find the first author frame without materializing the whole call stack."""
    frame = pyinspect.currentframe()
    try:
        while frame is not None:
            module = frame.f_globals.get("__name__", "")
            if module != "lecture" and not module.startswith("lecture."):
                return SourceLocation(
                    frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name
                )
            frame = frame.f_back
    finally:
        del frame
    return None


def _emit(kind: str, payload: dict[str, Any]) -> Event:
    from .media import collect_refs

    ctx = require_current()
    return ctx.emit(
        kind,
        payload,
        source_location=_caller_location(),
        artifact_refs=sorted(collect_refs(payload)),
    )


def text(markdown: str) -> Event:
    """Append markdown text (rendered to sanitized HTML at export)."""
    return _emit("text", {"markdown": markdown, "html": markdown_to_html(markdown)})


def code(source: str, language: str = "", title: str = "") -> Event:
    """Display source verbatim with a language label; never execute it."""
    from .formatting import code_payload

    return _emit("text", code_payload(source, language, title))


def table(
    rows: Iterable[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
    title: str = "Table",
    max_rows: int = 100,
) -> Event:
    """Render a bounded, accessible preview of records (default: first 100 rows)."""
    from .formatting import table_payload

    return _emit("text", table_payload(rows, columns=columns, title=title, max_rows=max_rows))


def note(markdown: str) -> Event:
    return _emit("note", {"markdown": markdown, "html": markdown_to_html(markdown)})


def asset(source: str | Path | bytes, *, mime: str | None = None) -> str:
    """Capture a local file/bytes for export, or retain an explicit remote URL."""
    from .media import capture_asset

    return capture_asset(source, mime=mime)


def image(
    src: str | Path | bytes, alt: str = "", title: str = "", *, mime: str | None = None
) -> Event:
    return _emit("image", {"src": asset(src, mime=mime), "alt": alt, "title": title})


def video(src: str | Path | bytes, title: str = "", *, mime: str | None = None) -> Event:
    return _emit("video", {"src": asset(src, mime=mime), "title": title})


def link(href: str, label: str = "") -> Event:
    return _emit("link", {"href": href, "label": label or href})


def plot(spec: dict[str, Any]) -> Event:
    """Vega/Vega-Lite (or compatible) spec dict — rendered by a renderer plugin."""
    if not isinstance(spec, dict):
        raise TypeError("plot(spec) expects a dict (Vega/Vega-Lite spec)")
    return _emit("plot", {"spec": spec})


def inspect_value(name: str, value: Any) -> Event:
    """Lazy inspector: large values travel as handle + preview, not eager JSON."""
    ctx = require_current()
    return ctx.inspect(name, value, source_location=_caller_location())


def clear() -> Event:
    return _emit("clear", {})


def whiteboard(
    title: str = "Whiteboard",
    *,
    width: int = 1200,
    height: int = 675,
    background: str = "grid",
) -> Event:
    """Spawn a local drawing surface with pen, shapes, text and portable exports.

    Runs in both static and live viewers. Pair Bluetooth styluses in the OS;
    browser Pointer Events supply pressure when supported. Drawing state is local
    to the viewer and survives stepping, but must be saved before reloading.
    """
    if not isinstance(title, str):
        raise TypeError("whiteboard title must be a string")
    if type(width) is not int or not 320 <= width <= 3840:
        raise ValueError("whiteboard width must be an integer from 320 to 3840")
    if type(height) is not int or not 180 <= height <= 2160:
        raise ValueError("whiteboard height must be an integer from 180 to 2160")
    if background not in {"blank", "grid", "dots"}:
        raise ValueError("whiteboard background must be blank, grid, or dots")
    return component(
        "whiteboard", {"title": title, "width": width, "height": height, "background": background}
    )


def _browser_window_id(window_id: str) -> str:
    import re

    if not isinstance(window_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", window_id):
        raise ValueError("browser window_id must contain 1-64 letters, numbers, '_' or '-'")
    return window_id


def _browser_url(url: str) -> str:
    from urllib.parse import urlsplit

    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 0x20 for c in url):
        raise ValueError("browser URL must be a printable string of at most 4096 characters")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("browser URL must be an absolute http:// or https:// URL")
    return url


def _browser_dimension(name: str, value: int, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"browser {name} must be an integer from {low} to {high}")
    return value


def _browser_position(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not -10_000 <= value <= 10_000:
        raise ValueError(f"browser {name} must be None or an integer from -10000 to 10000")
    return value


def browser_open(
    url: str,
    *,
    window_id: str = "reference",
    title: str = "Reference",
    width: int = 1200,
    height: int = 800,
    left: int | None = None,
    top: int | None = None,
    resizable: bool = True,
    focus: bool = True,
) -> Event:
    """Declare a user-initiated reference window for the browser viewer.

    The viewer renders an accessible Open button because browsers block
    unsolicited popups. In a user-activated Presenter or Inspector step
    transition, the viewer may also apply this recorded open automatically;
    the button and fallback link remain available if a popup is blocked. Once
    opened, the named window can be closed with ``browser_close(window_id)`` or
    its card's Close button.
    """
    from urllib.parse import urlsplit

    if not isinstance(title, str) or len(title) > 200:
        raise ValueError("browser title must be a string of at most 200 characters")
    if type(resizable) is not bool or type(focus) is not bool:
        raise TypeError("browser resizable and focus must be bools")
    clean_url = _browser_url(url)
    host = urlsplit(clean_url).netloc
    props = {
        "action": "open",
        "window_id": _browser_window_id(window_id),
        "url": clean_url,
        "title": title or clean_url,
        "width": _browser_dimension("width", width, 320, 4096),
        "height": _browser_dimension("height", height, 240, 2160),
        "left": _browser_position("left", left),
        "top": _browser_position("top", top),
        "resizable": resizable,
        "focus": focus,
    }
    return component("browser-window", props=props, permissions={"network": [host]})


def browser_close(window_id: str = "reference") -> Event:
    """Declare a close request for a previously opened reference window."""
    return component(
        "browser-window",
        props={"action": "close", "window_id": _browser_window_id(window_id)},
    )


def component(
    component_type: str,
    props: dict[str, Any] | None = None,
    permissions: dict[str, Any] | None = None,
) -> Event:
    """Stock or custom interactive component.

    Static export degrades to a recorded fallback (see export_static); live
    dispatch needs a broker ComponentService (v0.4+).
    """
    return _emit(
        "component",
        {
            "component_type": component_type,
            "props": dict(props or {}),
            "permissions": dict(permissions or {}),
            "fallback": "recorded",
        },
    )


@contextmanager
def section(
    name: str,
    *,
    tone: str = "neutral",
    density: str = "comfortable",
    width: str = "reading",
    align: str = "start",
):
    """Scope presentation hints for a coherent lecture section.

    Section hints are projection metadata only: they do not change execution,
    output ordering, or older readers. Use them around related calls to give a
    presenter a hero opening, compact evidence block, code/derivation passage,
    or spacious recap while keeping one portable event log.
    """
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError("section name must be a non-empty string of at most 80 characters")
    choices = {
        "tone": (tone, {"neutral", "hero", "evidence", "code", "recap"}),
        "density": (density, {"compact", "comfortable", "roomy"}),
        "width": (width, {"reading", "wide", "full"}),
        "align": (align, {"start", "center"}),
    }
    for label, (value, allowed) in choices.items():
        if value not in allowed:
            raise ValueError(f"section {label} must be one of {sorted(allowed)}")
    ctx = require_current()
    with ctx.presentation_scope(
        {"name": name.strip(), "tone": tone, "density": density, "width": width, "align": align}
    ):
        yield


def terminal(argv: list[str], mode: str = "recorded", policy: str = "lecture-process") -> Event:
    """Declare a terminal/process block. Live PTY needs the broker (v0.3+)."""
    return _emit("terminal", {"argv": list(argv), "mode": mode, "policy": policy})


def system_text(command: list[str] | str, *, max_bytes: int = 64_000) -> Event:
    """Brokered one-shot process convenience (replaces edtrace's check_output).

    Policy-enforced: raises PolicyViolation unless the active profile allows
    process execution. Output is truncated with backpressure (never buffered
    unboundedly) and ANSI escapes are stripped.
    """
    from .policy import check_process

    ctx = require_current()
    argv = command if isinstance(command, list) else _split(command)
    check_process(ctx.policy, argv)
    try:
        raw = subprocess.check_output(
            argv, stderr=subprocess.STDOUT, timeout=ctx.policy.max_wall_seconds
        )
    except subprocess.CalledProcessError as e:
        out = (e.output or b"")[:max_bytes]
        clean = _strip_ansi(out.decode("utf-8", errors="replace"))
        ev = ctx.emit(
            "terminal",
            {"argv": argv, "output": clean, "exit_code": e.returncode},
            source_location=_caller_location(),
        )
        return ev
    except Exception as e:  # timeout / missing binary → error event, not crash
        return ctx.emit(
            "error", {"message": f"system_text failed: {e}"}, source_location=_caller_location()
        )
    data = raw[: max(ctx.policy.max_output_bytes, max_bytes)]
    clean = _strip_ansi(data.decode("utf-8", errors="replace"))
    if len(raw) > len(data):
        clean += f"\n…[truncated {len(raw) - len(data)} bytes]"
    return ctx.emit(
        "terminal",
        {"argv": argv, "output": clean, "exit_code": 0},
        source_location=_caller_location(),
    )


def _split(cmd: str) -> list[str]:
    import shlex

    return shlex.split(cmd)


def _strip_ansi(s: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)


# -- structured directives (preferred over comment parsing over time) ----------


def inspect(*names: str) -> Callable:
    """Decorator: always capture these locals at each traced line in scope."""

    def deco(fn: Callable) -> Callable:
        existing = getattr(fn, "__lecture_inspect__", ())
        fn.__lecture_inspect__ = tuple(existing) + tuple(names)  # type: ignore[attr-defined]

        @functools.wraps(fn)
        def wrapper(*a: Any, **k: Any) -> Any:
            return fn(*a, **k)

        wrapper.__lecture_inspect__ = fn.__lecture_inspect__  # type: ignore[attr-defined]
        for marker in ("__lecture_hide__", "__lecture_step_over__"):
            if hasattr(fn, marker):
                setattr(wrapper, marker, getattr(fn, marker))
        return wrapper

    return deco


def hide(fn: Callable) -> Callable:
    """Decorator: hide helper from pedagogical stepping."""
    fn.__lecture_hide__ = True  # type: ignore[attr-defined]

    @functools.wraps(fn)
    def wrapper(*a: Any, **k: Any) -> Any:
        return fn(*a, **k)

    wrapper.__lecture_hide__ = True  # type: ignore[attr-defined]
    if hasattr(fn, "__lecture_inspect__"):
        wrapper.__lecture_inspect__ = fn.__lecture_inspect__  # type: ignore[attr-defined]
    return wrapper


def step_over(fn: Callable) -> Callable:
    """Decorator: trace calls to this function as a single step (no descent)."""
    fn.__lecture_step_over__ = True  # type: ignore[attr-defined]

    @functools.wraps(fn)
    def wrapper(*a: Any, **k: Any) -> Any:
        return fn(*a, **k)

    wrapper.__lecture_step_over__ = True  # type: ignore[attr-defined]
    return wrapper
