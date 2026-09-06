"""Versioned lecture event protocol (v1).

Single-writer ordered event log for *execution* state. Never a CRDT:
shell commands, file writes, GPU kernels are not commutative edits.
CRDTs (Yjs/Automerge) are reserved for collaboratively edited *source* (v0.5+).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = 1

EVENT_KINDS = frozenset(
    {
        "session_start",
        "session_end",
        "step",
        "text",
        "note",
        "image",
        "video",
        "link",
        "plot",
        "inspect",
        "clear",
        "error",
        "terminal",
        "component",
        "snapshot",
    }
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class SourceLocation:
    file: str
    line: int
    func: str = "main"

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "func": self.func}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceLocation:
        return cls(file=str(d["file"]), line=int(d["line"]), func=str(d.get("func", "main")))


@dataclass
class Event:
    session_id: str
    execution_id: str
    seq: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    wall_time: float = field(default_factory=time.time)
    source_location: SourceLocation | None = None
    artifact_refs: list[str] = field(default_factory=list)
    parent_event: int | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "session_id": self.session_id,
            "execution_id": self.execution_id,
            "seq": self.seq,
            "wall_time": self.wall_time,
            "kind": self.kind,
            "payload": self.payload,
            "artifact_refs": list(self.artifact_refs),
            "schema_version": self.schema_version,
        }
        if self.source_location is not None:
            d["source_location"] = self.source_location.to_dict()
        if self.parent_event is not None:
            d["parent_event"] = self.parent_event
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        loc = d.get("source_location")
        return cls(
            session_id=str(d["session_id"]),
            execution_id=str(d["execution_id"]),
            seq=int(d["seq"]),
            kind=str(d["kind"]),
            payload=dict(d.get("payload", {})),
            wall_time=float(d.get("wall_time", 0.0)),
            source_location=SourceLocation.from_dict(loc) if loc else None,
            artifact_refs=list(d.get("artifact_refs", [])),
            parent_event=d.get("parent_event"),
            schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
        )


def validate_event(d: dict[str, Any]) -> list[str]:
    """Return a list of validation errors (empty == valid)."""
    errors: list[str] = []
    for key in ("session_id", "execution_id", "seq", "kind"):
        if key not in d:
            errors.append(f"missing required field: {key}")
    if "kind" in d and d["kind"] not in EVENT_KINDS:
        errors.append(f"unknown kind: {d.get('kind')!r}")
    if "seq" in d and (not isinstance(d["seq"], int) or d["seq"] < 0):
        errors.append("seq must be a non-negative int")
    if d.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {d.get('schema_version')!r}")
    loc = d.get("source_location")
    if loc is not None:
        if not isinstance(loc, dict) or "file" not in loc or "line" not in loc:
            errors.append("source_location must be {file, line, [func]}")
    refs = d.get("artifact_refs", [])
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
        errors.append("artifact_refs must be a list of strings")
    for r in refs if isinstance(refs, list) else []:
        if isinstance(r, str) and not r.startswith("sha256:"):
            errors.append(f"artifact ref must start with 'sha256:': {r!r}")
    payload = d.get("payload", {})
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
    return errors


class EventLog:
    """In-memory single-writer ordered log. Reconnection = subscribe(after_seq)."""

    def __init__(self, session_id: str, execution_id: str) -> None:
        self.session_id = session_id
        self.execution_id = execution_id
        self._events: list[Event] = []
        self._next_seq = 0

    def __len__(self) -> int:
        return len(self._events)

    def append(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        source_location: SourceLocation | None = None,
        artifact_refs: list[str] | None = None,
        parent_event: int | None = None,
    ) -> Event:
        if kind not in EVENT_KINDS:
            raise ValueError(f"unknown event kind: {kind!r}")
        ev = Event(
            session_id=self.session_id,
            execution_id=self.execution_id,
            seq=self._next_seq,
            kind=kind,
            payload=dict(payload or {}),
            source_location=source_location,
            artifact_refs=list(artifact_refs or []),
            parent_event=parent_event,
        )
        errors = validate_event(ev.to_dict())
        if errors:
            raise ValueError(f"invalid event: {errors}")
        self._events.append(ev)
        self._next_seq += 1
        return ev

    def subscribe(self, after_seq: int = -1) -> list[Event]:
        """Return events with seq > after_seq (deterministic replay primitive)."""
        return [e for e in self._events if e.seq > after_seq]

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]

    @classmethod
    def from_list(cls, session_id: str, execution_id: str, items: list[dict[str, Any]]) -> EventLog:
        log = cls(session_id, execution_id)
        for item in items:
            errors = validate_event(item)
            if errors:
                raise ValueError(f"invalid stored event: {errors}")
            ev = Event.from_dict(item)
            # Enforce monotonic seq on load so corrupted/tampered logs fail fast.
            if ev.seq != log._next_seq:
                raise ValueError(f"non-monotonic seq: expected {log._next_seq}, got {ev.seq}")
            log._events.append(ev)
            log._next_seq += 1
        return log

    def check_monotonic(self) -> bool:
        return all(e.seq == i for i, e in enumerate(self._events))


def replay_to_presentation(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Blank-client reconstruction: same sequence → identical presentation state.

    Used by golden replay tests. Returns {steps, outputs, inspect_state}.
    """
    steps: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    inspect_state: dict[str, Any] = {}
    for item in events:
        kind = item.get("kind")
        if kind == "step":
            steps.append(item.get("payload", {}))
        elif kind in ("text", "note", "image", "video", "link", "plot", "terminal", "component"):
            outputs.append({"kind": kind, **item.get("payload", {})})
        elif kind == "inspect":
            payload = item.get("payload", {})
            if "name" in payload:
                inspect_state[str(payload["name"])] = payload.get("summary")
        elif kind == "clear":
            outputs.clear()
            inspect_state.clear()
    return {"steps": steps, "outputs": outputs, "inspect_state": inspect_state}
