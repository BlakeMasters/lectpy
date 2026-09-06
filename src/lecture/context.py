"""Scoped execution context — replaces edtrace's process-global accumulator.

Author code calls plain `text(...)` / `inspect_value(...)` without threading a
handle through every call, but state is scoped via ContextVar (async-safe and
concurrent-session-safe), never a module-global list.
"""

from __future__ import annotations

import contextvars
import reprlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from .artifacts import ArtifactStore
from .events import Event, EventLog, SourceLocation, new_id
from .policy import GrantedPolicy, default_policy

_current: contextvars.ContextVar[ExecutionContext | None] = contextvars.ContextVar(
    "lecture_current_context", default=None
)

MAX_REPR_LEN = 2000
MAX_PREVIEW_LEN = 500


def _summarize(value: Any) -> dict[str, Any]:
    """Small summary always; large values get preview + lazy handle (v0.1 in-mem)."""
    r = reprlib.repr(value)
    summary = r if len(r) <= MAX_REPR_LEN else r[:MAX_REPR_LEN] + "…"
    info: dict[str, Any] = {"summary": summary, "type": type(value).__name__}
    try:
        if isinstance(value, (list, tuple)):
            info["len"] = len(value)
            info["preview"] = reprlib.repr(value[:10])
        elif isinstance(value, dict):
            info["len"] = len(value)
            info["preview"] = reprlib.repr(dict(list(value.items())[:10]))
        elif isinstance(value, (bytes, bytearray)):
            info["len"] = len(value)
            info["preview"] = f"<{len(value)} bytes>"
        elif hasattr(value, "shape") and hasattr(value, "dtype"):
            # numpy/torch-like without importing them
            try:
                info["shape"] = list(value.shape)  # type: ignore[union-attr]
            except Exception:
                pass
            try:
                info["dtype"] = str(value.dtype)
            except Exception:
                pass
            info["preview"] = summary[:MAX_PREVIEW_LEN]
        elif isinstance(value, str) and len(value) > MAX_PREVIEW_LEN:
            info["len"] = len(value)
            info["preview"] = value[:MAX_PREVIEW_LEN] + "…"
    except Exception:
        pass
    return info


@dataclass
class ExecutionContext:
    session_id: str = field(default_factory=lambda: new_id("sess"))
    execution_id: str = field(default_factory=lambda: new_id("exec"))
    source_file: str = "<lecture>"
    policy: GrantedPolicy = field(default_factory=lambda: default_policy("local-trusted"))
    artifacts: ArtifactStore | None = None
    log: EventLog = field(init=False)
    _objects: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _obj_counter: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        self.log = EventLog(self.session_id, self.execution_id)

    # -- object handles (lazy inspector) -------------------------------------
    def register_object(self, value: Any) -> str:
        handle = f"obj:{self.execution_id}:{self._obj_counter}"
        self._obj_counter += 1
        self._objects[handle] = value
        return handle

    def get_object(self, handle: str) -> Any:
        try:
            return self._objects[handle]
        except KeyError:
            raise KeyError(f"unknown or released object handle: {handle}") from None

    def release_object(self, handle: str) -> None:
        self._objects.pop(handle, None)

    # -- emit -----------------------------------------------------------------
    def emit(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        line: int | None = None,
        func: str = "main",
        artifact_refs: list[str] | None = None,
    ) -> Event:
        loc = None
        if line is not None:
            loc = SourceLocation(file=self.source_file, line=line, func=func)
        if len(self.log) >= self.policy.max_events:
            raise RuntimeError(f"event budget exceeded ({self.policy.max_events})")
        return self.log.append(
            kind, payload or {}, source_location=loc, artifact_refs=artifact_refs
        )

    def inspect(self, name: str, value: Any, *, line: int | None = None) -> Event:
        info = _summarize(value)
        payload: dict[str, Any] = {"name": name, **info}
        # Large values stay behind a handle; only preview crosses the event log.
        if len(info.get("summary", "")) >= MAX_REPR_LEN or info.get("len", 0) > 1000:
            payload["handle"] = self.register_object(value)
        return self.emit("inspect", payload, line=line)


def get_current() -> ExecutionContext | None:
    return _current.get()


def require_current() -> ExecutionContext:
    ctx = _current.get()
    if ctx is None:
        raise RuntimeError(
            "lecture author primitives called outside an ExecutionContext. "
            "Run via `lecture trace` or wrap code in `with execution_scope(...):`."
        )
    return ctx


@contextmanager
def execution_scope(
    ctx: ExecutionContext | None = None, **kwargs: Any
) -> Iterator[ExecutionContext]:
    ctx = ctx or ExecutionContext(**kwargs)
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)
