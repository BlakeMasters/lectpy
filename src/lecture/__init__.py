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
    "video",
    "link",
    "plot",
    "inspect_value",
    "clear",
    "system_text",
    "component",
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
    ctx = require_current()
    return ctx.emit(kind, payload, source_location=_caller_location())


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


def image(src: str, alt: str = "", title: str = "") -> Event:
    return _emit("image", {"src": src, "alt": alt, "title": title})


def video(src: str, title: str = "") -> Event:
    return _emit("video", {"src": src, "title": title})


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
