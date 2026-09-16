"""Author-facing SDK — plain Python executable lectures.

Level A needs no frontend code. Every primitive emits a typed event on the
scoped ExecutionContext (ContextVar), so concurrent sessions never share the
legacy process-global `_current_renderings` accumulator.
"""

from __future__ import annotations

import functools
import inspect as pyinspect
import json
import math
import re
import subprocess
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .context import MAX_STEP_KEYABLES, require_current
from .events import Event, SourceLocation
from .options import PresentationStyle, WhiteboardOptions
from .sanitize import markdown_to_html

__all__ = [
    "PresentationStyle",
    "WhiteboardOptions",
    "text",
    "code",
    "table",
    "note",
    "image",
    "asset",
    "video",
    "link",
    "plot",
    "step_playback",
    "step_keyables",
    "equation",
    "uml",
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


def _output_id(value: str | None) -> str | None:
    """Validate a stable author id used to connect related visual outputs."""
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError(
            "output_id must start with a letter or number and contain at most 64 "
            "letters, numbers, '_' or '-'"
        )
    return value


def text(markdown: str) -> Event:
    """Append markdown text (rendered to sanitized HTML at export)."""
    return _emit("text", {"markdown": markdown, "html": markdown_to_html(markdown)})


def code(
    source: str,
    language: str = "",
    title: str = "",
    *,
    output_id: str | None = None,
) -> Event:
    """Display source verbatim with a language label; never execute it."""
    from .formatting import code_payload

    return _emit("text", code_payload(source, language, title, output_id=_output_id(output_id)))


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


_STEP_PLAYBACK_MAX_SERIES = 6
_STEP_PLAYBACK_MAX_PANELS = 3
_STEP_PLAYBACK_MAX_STEPS = 400
_STEP_PLAYBACK_MAX_LABEL = 160
_STEP_KEYABLE_MAX_KEY = 64
_STEP_KEYABLE_ACTIONS = {
    "step.first",
    "step.previous",
    "step.next",
    "step.over",
    "step.last",
    "playback.play",
    "playback.pause",
    "playback.toggle",
    "playback.replay",
}
_STEP_KEYABLE_ALIASES = {
    "first": "step.first",
    "previous": "step.previous",
    "back": "step.previous",
    "next": "step.next",
    "forward": "step.next",
    "over": "step.over",
    "last": "step.last",
    "play": "playback.play",
    "pause": "playback.pause",
    "toggle": "playback.toggle",
    "replay": "playback.replay",
}


def _step_playback_label(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    if not isinstance(value, str):
        raise TypeError("step_playback labels must be strings")
    return value[:_STEP_PLAYBACK_MAX_LABEL]


def _step_keyable_key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > _STEP_KEYABLE_MAX_KEY:
        raise ValueError(
            "step keyable keys must be non-empty strings of at most "
            f"{_STEP_KEYABLE_MAX_KEY} characters"
        )
    parts = value.strip().split("+")
    key = parts.pop()
    if not key:
        raise ValueError("step keyable keys must end with a key name")
    if key == "Spacebar":
        key = "Space"
    if len(key) == 1 and key.isascii() and key.isalpha():
        key = key.lower()
    aliases = {
        "ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "option": "Alt",
        "shift": "Shift", "cmd": "Meta", "command": "Meta", "meta": "Meta",
    }
    modifiers: set[str] = set()
    for part in parts:
        modifier = aliases.get(part.lower())
        if modifier is None or modifier in modifiers:
            raise ValueError(f"invalid or duplicate step keyable modifier: {part}")
        modifiers.add(modifier)
    return "+".join([mod for mod in ("Ctrl", "Alt", "Shift", "Meta") if mod in modifiers] + [key])


def _step_keyable_action(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("step keyable actions must be strings")
    action = value.strip().lower().replace("_", ".")
    action = _STEP_KEYABLE_ALIASES.get(action, action)
    if action not in _STEP_KEYABLE_ACTIONS:
        allowed = ", ".join(sorted(_STEP_KEYABLE_ACTIONS))
        raise ValueError(f"unsupported step keyable action {value!r}; use one of {allowed}")
    return action


def _normalize_step_keyables(
    bindings: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    default_target: str | None = None,
) -> list[dict[str, Any]]:
    if isinstance(bindings, Mapping):
        raw_items: list[tuple[Any, Any]] = list(bindings.items())
    elif isinstance(bindings, (str, bytes)) or not isinstance(bindings, Sequence):
        raise TypeError(
            "step keyables must be a mapping of key to action or a sequence of mappings"
        )
    else:
        raw_items = []
        for entry in bindings:
            if not isinstance(entry, Mapping):
                raise TypeError("step keyable entries must be mappings")
            raw_items.append((entry.get("key"), entry))
    if len(raw_items) > MAX_STEP_KEYABLES:
        raise ValueError(f"step_keyables supports at most {MAX_STEP_KEYABLES} bindings")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_key, raw_value in raw_items:
        key = _step_keyable_key(raw_key)
        if key in seen:
            raise ValueError(f"duplicate step keyable key: {key}")
        seen.add(key)
        if isinstance(raw_value, str):
            action = _step_keyable_action(raw_value)
            config: Mapping[str, Any] = {}
        elif isinstance(raw_value, Mapping):
            action = _step_keyable_action(raw_value.get("action"))
            config = raw_value
        else:
            raise TypeError("step keyable values must be action strings or mappings")
        target = config.get("target", default_target)
        if target is not None:
            target = _output_id(target)
        label = config.get("label")
        if label is None:
            label = action.replace(".", " ")
        label = _step_playback_label(label, action.replace(".", " "))
        prevent_default = config.get("prevent_default", True)
        if type(prevent_default) is not bool:
            raise TypeError("step keyable prevent_default must be a bool")
        item: dict[str, Any] = {
            "key": key,
            "action": action,
            "label": label,
            "prevent_default": prevent_default,
        }
        if target is not None:
            item["target"] = target
        normalized.append(item)
    return normalized


@contextmanager
def step_keyables(
    bindings: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> Iterator[None]:
    """Scope safe keyboard actions to lecture events emitted in this block.

    Keys may map to aliases such as ``"playback.pause"``/``"pause"`` or to
    mappings with ``action``, ``target`` and ``label`` fields. The viewer only
    executes the finite step/playback action vocabulary; it never evaluates
    arbitrary Python or JavaScript from a key binding.
    """
    ctx = require_current()
    with ctx.step_keyable_scope(_normalize_step_keyables(bindings)):
        yield


def _step_playback_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"step_playback {field} values must be finite numbers")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"step_playback {field} values must be finite numbers")
    return number


def _step_playback_sequence(value: Any, field: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"step_playback {field} must be a sequence")
    return value


def _step_playback_trajectory_series(entry: Any, index: int) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise TypeError("step_playback trajectory series must be mappings")
    raw_points = _step_playback_sequence(entry.get("points"), "trajectory points")
    if not 2 <= len(raw_points) <= _STEP_PLAYBACK_MAX_STEPS + 1:
        raise ValueError(
            f"step_playback trajectory points must contain 2–{_STEP_PLAYBACK_MAX_STEPS + 1} samples"
        )
    points: list[dict[str, float]] = []
    for point_index, point in enumerate(raw_points):
        if isinstance(point, Mapping):
            x, y = point.get("x"), point.get("y")
        elif (
            isinstance(point, Sequence)
            and not isinstance(point, (str, bytes))
            and len(point) == 2
        ):
            x, y = point[0], point[1]
        else:
            raise TypeError(f"step_playback trajectory point {point_index} must contain x and y")
        points.append(
            {
                "x": _step_playback_number(x, "trajectory x"),
                "y": _step_playback_number(y, "trajectory y"),
            }
        )
    series_id = _step_playback_label(entry.get("id"), f"trajectory-{index + 1}")
    return {
        "id": series_id,
        "label": _step_playback_label(entry.get("label"), series_id),
        "points": points,
    }


def _step_playback_response_series(entry: Any, index: int, step_count: int) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        raise TypeError("step_playback response series must be mappings")
    raw_values = _step_playback_sequence(entry.get("values"), "response values")
    if len(raw_values) != step_count + 1:
        raise ValueError(
            "step_playback response values must have exactly step_count + 1 samples"
        )
    series_id = _step_playback_label(entry.get("id"), f"response-{index + 1}")
    return {
        "id": series_id,
        "label": _step_playback_label(entry.get("label"), series_id),
        "values": [_step_playback_number(value, "response") for value in raw_values],
    }


def step_playback(
    trajectory: Mapping[str, Any],
    responses: Sequence[Mapping[str, Any]],
    *,
    title: str = "Step playback",
    alt: str = "",
    output_id: str | None = None,
    autoplay_on_step: bool = False,
    restart_on_enter: bool = False,
    pause_on_leave: bool = True,
    keyables: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
) -> Event:
    """Emit a bounded, replay-local trajectory and response playback figure.

    ``trajectory`` contains ``series`` with ``points`` and may include
    ``contours`` (numeric levels) and a ``target`` point. ``responses`` is a
    sequence of panels; each panel contains ``series`` with ``values`` and
    optional ``references`` of ``{value, label, tone}``. All series share the
    inferred step count, and the browser never resumes Python to animate them.

    ``autoplay_on_step`` starts the figure when its output becomes current in
    Presenter/Inspector. ``restart_on_enter`` resets it before that start, and
    ``pause_on_leave`` pauses it when the lecture moves to another step. The
    optional ``keyables`` mapping attaches safe keyboard actions to this output;
    when omitted, Up plays, Down pauses, and Space toggles the playback.
    """
    for field, value in (
        ("autoplay_on_step", autoplay_on_step),
        ("restart_on_enter", restart_on_enter),
        ("pause_on_leave", pause_on_leave),
    ):
        if type(value) is not bool:
            raise TypeError(f"step_playback {field} must be a bool")
    if not isinstance(trajectory, Mapping):
        raise TypeError("step_playback trajectory must be a mapping")
    raw_trajectory_series = _step_playback_sequence(
        trajectory.get("series"), "trajectory series"
    )
    if not 1 <= len(raw_trajectory_series) <= _STEP_PLAYBACK_MAX_SERIES:
        raise ValueError(
            f"step_playback supports 1–{_STEP_PLAYBACK_MAX_SERIES} trajectory series"
        )
    trajectory_series = [
        _step_playback_trajectory_series(entry, index)
        for index, entry in enumerate(raw_trajectory_series)
    ]
    point_counts = {len(series["points"]) for series in trajectory_series}
    if len(point_counts) != 1:
        raise ValueError("step_playback trajectory series must have the same sample count")
    step_count = next(iter(point_counts)) - 1
    if not 1 <= step_count <= _STEP_PLAYBACK_MAX_STEPS:
        raise ValueError(
            f"step_playback step count must be between 1 and {_STEP_PLAYBACK_MAX_STEPS}"
        )

    if isinstance(responses, (str, bytes)) or not isinstance(responses, Sequence):
        raise TypeError("step_playback responses must be a sequence")
    if not 1 <= len(responses) <= _STEP_PLAYBACK_MAX_PANELS:
        raise ValueError(
            f"step_playback supports 1–{_STEP_PLAYBACK_MAX_PANELS} response panels"
        )
    normalized_responses: list[dict[str, Any]] = []
    for panel_index, panel in enumerate(responses):
        if not isinstance(panel, Mapping):
            raise TypeError("step_playback response panels must be mappings")
        raw_series = _step_playback_sequence(panel.get("series"), "response series")
        if not 1 <= len(raw_series) <= _STEP_PLAYBACK_MAX_SERIES:
            raise ValueError(
                f"step_playback response panels support 1–{_STEP_PLAYBACK_MAX_SERIES} series"
            )
        series = [
            _step_playback_response_series(entry, index, step_count)
            for index, entry in enumerate(raw_series)
        ]
        raw_references = panel.get("references", ())
        if raw_references is None:
            raw_references = ()
        raw_references = _step_playback_sequence(raw_references, "references")
        references: list[dict[str, Any]] = []
        for reference in raw_references[: _STEP_PLAYBACK_MAX_SERIES]:
            if not isinstance(reference, Mapping):
                raise TypeError("step_playback references must be mappings")
            tone = reference.get("tone", "muted")
            if tone not in {"muted", *[f"series-{i}" for i in range(1, 7)]}:
                raise ValueError("step_playback reference tone must be muted or series-1…series-6")
            references.append(
                {
                    "value": _step_playback_number(reference.get("value"), "reference"),
                    "label": _step_playback_label(reference.get("label"), "reference"),
                    "tone": tone,
                }
            )
        normalized_responses.append(
            {
                "id": _step_playback_label(panel.get("id"), f"panel-{panel_index + 1}"),
                "title": _step_playback_label(panel.get("title"), f"Response {panel_index + 1}"),
                "y_label": _step_playback_label(panel.get("y_label"), "value"),
                "series": series,
                "references": references,
            }
        )

    raw_contours = trajectory.get("contours", ())
    if raw_contours is None:
        raw_contours = ()
    raw_contours = _step_playback_sequence(raw_contours, "contours")
    contours: list[dict[str, Any]] = []
    for contour in raw_contours[:12]:
        if isinstance(contour, Mapping):
            level = contour.get("level")
            dashed = bool(contour.get("dashed", False))
        else:
            level = contour
            dashed = False
        contours.append({"level": _step_playback_number(level, "contour"), "dashed": dashed})

    target = trajectory.get("target")
    normalized_target = None
    if target is not None:
        if not isinstance(target, Mapping):
            raise TypeError("step_playback target must be a mapping")
        normalized_target = {
            "x": _step_playback_number(target.get("x"), "target x"),
            "y": _step_playback_number(target.get("y"), "target y"),
            "label": _step_playback_label(target.get("label"), "equilibrium"),
        }

    normalized_output_id = _output_id(output_id)
    if keyables is None:
        keyables = {
            "ArrowUp": {"action": "playback.play", "label": "Play playback"},
            "ArrowDown": {"action": "playback.pause", "label": "Pause playback"},
            "Space": {"action": "playback.toggle", "label": "Toggle playback"},
        }
    normalized_keyables = _normalize_step_keyables(
        keyables,
        default_target=normalized_output_id,
    )

    return component(
        "step-playback",
        props={
            "title": _step_playback_label(title, "Step playback"),
            "alt": _step_playback_label(alt, "Synchronized step playback figure."),
            "output_id": normalized_output_id,
            "step_trigger": {
                "autoplay_on_step": autoplay_on_step,
                "restart_on_enter": restart_on_enter,
                "pause_on_leave": pause_on_leave,
            },
            "step_count": step_count,
            "trajectory": {
                "x_label": _step_playback_label(trajectory.get("x_label"), "x"),
                "y_label": _step_playback_label(trajectory.get("y_label"), "y"),
                "series": trajectory_series,
                "contours": contours,
                "target": normalized_target,
            },
            "responses": normalized_responses,
        },
        keyables=normalized_keyables,
    )


def equation(
    tex: str,
    *,
    display: bool = True,
    alt: str = "",
    title: str = "",
    output_id: str | None = None,
) -> Event:
    """Render a bounded TeX equation with a native MathML fallback.

    The event keeps the original TeX rather than embedding renderer HTML. The
    static and React viewers use the same small renderer, so bundles remain
    offline and do not require a KaTeX/MathJax download.
    """
    if not isinstance(tex, str) or not tex.strip() or len(tex) > 12_000:
        raise ValueError("equation tex must be a non-empty string of at most 12000 characters")
    if type(display) is not bool:
        raise TypeError("equation display must be a bool")
    if not isinstance(alt, str) or len(alt) > 500:
        raise ValueError("equation alt must be a string of at most 500 characters")
    if not isinstance(title, str) or len(title) > 200:
        raise ValueError("equation title must be a string of at most 200 characters")
    payload: dict[str, Any] = {
        "tex": tex,
        "display": display,
        "alt": alt or f"Equation: {tex}",
        "title": title,
    }
    if (clean_id := _output_id(output_id)) is not None:
        payload["output_id"] = clean_id
    return _emit("equation", payload)


def uml(
    kind: str,
    spec: Mapping[str, Any],
    *,
    title: str = "",
    alt: str = "",
    output_id: str | None = None,
) -> Event:
    """Render a structured UML class or sequence diagram.

    ``spec`` is deliberately data, not a renderer-specific SVG/string. This
    gives static and live viewers a safe visual plus a text description and
    leaves room for alternate renderers without changing lecture source.
    """
    if kind not in {"class", "sequence"}:
        raise ValueError("uml kind must be 'class' or 'sequence'")
    if not isinstance(spec, Mapping):
        raise TypeError("uml spec must be a mapping")
    try:
        encoded = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise TypeError("uml spec must contain JSON-compatible values") from exc
    if len(encoded.encode("utf-8")) > 200_000:
        raise ValueError("uml spec must be at most 200000 UTF-8 bytes")
    if not isinstance(title, str) or len(title) > 200:
        raise ValueError("uml title must be a string of at most 200 characters")
    if not isinstance(alt, str) or len(alt) > 1000:
        raise ValueError("uml alt must be a string of at most 1000 characters")
    payload: dict[str, Any] = {
        "uml_kind": kind,
        "spec": dict(spec),
        "title": title,
        "alt": alt or f"UML {kind} diagram",
    }
    if (clean_id := _output_id(output_id)) is not None:
        payload["output_id"] = clean_id
    return _emit("uml", payload)


def inspect_value(name: str, value: Any) -> Event:
    """Lazy inspector: large values travel as handle + preview, not eager JSON."""
    ctx = require_current()
    return ctx.inspect(name, value, source_location=_caller_location())


def clear() -> Event:
    return _emit("clear", {})


def whiteboard(
    title: str = "Whiteboard",
    *,
    options: WhiteboardOptions | None = None,
    width: int | None = None,
    height: int | None = None,
    background: str | None = None,
    insertable: bool | None = None,
    tool: str | None = None,
    color: str | None = None,
    stroke_width: int | None = None,
    close_on_insert: bool | None = None,
    output_id: str | None = None,
    alt: str = "",
) -> Event:
    """Spawn a local drawing surface with pen, shapes, text and portable exports.

    Runs in both static and live viewers. Pair Bluetooth styluses in the OS;
    browser Pointer Events supply pressure when supported. Drawing state is local
    to the viewer and survives stepping, but must be saved before reloading.
    Reuse ``WhiteboardOptions`` with ``options=...``; explicit keywords override
    its defaults. ``close_on_insert=True`` closes the editor after a snapshot.
    """
    if not isinstance(title, str):
        raise TypeError("whiteboard title must be a string")
    if options is not None and not isinstance(options, WhiteboardOptions):
        raise TypeError("whiteboard options must be WhiteboardOptions")
    overrides = {
        "width": width,
        "height": height,
        "background": background,
        "insertable": insertable,
        "tool": tool,
        "color": color,
        "stroke_width": stroke_width,
        "close_on_insert": close_on_insert,
    }
    resolved = (options or WhiteboardOptions()).with_options(
        **{k: v for k, v in overrides.items() if v is not None}
    )
    if not isinstance(alt, str) or len(alt) > 1000:
        raise ValueError("whiteboard alt must be a string of at most 1000 characters")
    props: dict[str, Any] = {"title": title, **resolved.to_props()}
    if (clean_id := _output_id(output_id)) is not None:
        props["output_id"] = clean_id
    if alt:
        props["alt"] = alt
    return component("whiteboard", props)


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
    *,
    keyables: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
) -> Event:
    """Stock or custom interactive component.

    Static export degrades to a recorded fallback (see export_static); live
    dispatch needs a broker ComponentService (v0.4+).
    """
    payload: dict[str, Any] = {
        "component_type": component_type,
        "props": dict(props or {}),
        "permissions": dict(permissions or {}),
        "fallback": "recorded",
    }
    if keyables is not None:
        payload["step_keyables"] = _normalize_step_keyables(keyables)
    return _emit("component", payload)


@contextmanager
def section(
    name: str,
    *,
    style: PresentationStyle | None = None,
    tone: str | None = None,
    density: str | None = None,
    width: str | None = None,
    align: str | None = None,
    font: str | None = None,
    text_size: str | None = None,
    highlight: str | None = None,
    focus: str | None = None,
    controls: Sequence[Any] = (),
):
    """Scope presentation hints for a coherent lecture section.

    Section hints are projection metadata only: they do not change execution,
    output ordering, or older readers. Use them around related calls to give a
    presenter a hero opening, compact evidence block, code/derivation passage,
    or spacious recap while keeping one portable event log.
    Keywords override ``style``. Without a style, nested sections inherit their
    enclosing section; top-level sections use ``PresentationStyle()`` defaults.
    """
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError("section name must be a non-empty string of at most 80 characters")
    ctx = require_current()
    if style is not None and not isinstance(style, PresentationStyle):
        raise TypeError("section style must be PresentationStyle")
    base = style or PresentationStyle(**ctx.presentation_options)
    overrides = {
        "tone": tone,
        "density": density,
        "width": width,
        "align": align,
        "font": font,
        "text_size": text_size,
        "highlight": highlight,
        "focus": focus,
    }
    resolved = base.with_options(**{k: v for k, v in overrides.items() if v is not None})
    from .browser import PlaywrightControls

    if not isinstance(controls, (tuple, list)) or not all(
        isinstance(control, PlaywrightControls) for control in controls
    ):
        raise TypeError("section controls must be a tuple/list of PlaywrightControls")
    if len({control.id for control in controls}) != len(controls):
        raise ValueError("section control ids must be unique")
    bindings = [f"{ctx.execution_id}:{len(ctx.log)}:{control.id}" for control in controls]
    with (
        ctx.presentation_scope({"name": name.strip(), **resolved.to_dict()}),
        ctx.control_scope(bindings),
    ):
        for control, binding in zip(controls, bindings, strict=True):
            component("playwright-controls", {**control.to_props(), "binding_id": binding})
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
