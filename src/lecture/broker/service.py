"""In-process capability broker (local single-user core of `lectured`).

All privileged actions flow through here: session open/close, execution
dispatch to providers, ordered event subscription, artifact proxy, policy
enforcement. Transports (loopback WS/UDS/named-pipe locally, TLS WS remotely
in later milestones) all speak this same logical API — never PIDs or host
paths on the wire.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..context import ExecutionContext
from ..events import Event
from ..ir import Checkpoint
from ..policy import GrantedPolicy, default_policy
from ..trace import TraceExecutor


@dataclass
class Session:
    session_id: str
    document: str
    policy: GrantedPolicy
    ctx: ExecutionContext


class InProcessBroker:
    """Local broker: one process, child runtimes, no network listeners (v0.1)."""

    def __init__(self, artifact_root: str | Path = ".lecture/artifacts") -> None:
        self.artifacts = ArtifactStore(artifact_root)
        self._sessions: dict[str, Session] = {}

    # -- SessionService ------------------------------------------------------
    def open(
        self,
        document: str = "",
        environment: dict | None = None,
        policy_profile: str = "local-trusted",
    ) -> Session:
        policy = default_policy(policy_profile)
        ctx = ExecutionContext(
            source_file=document or "<lecture>", policy=policy, artifacts=self.artifacts
        )
        sess = Session(session_id=ctx.session_id, document=document, policy=policy, ctx=ctx)
        self._sessions[sess.session_id] = sess
        ctx.emit(
            "session_start",
            {"document": document, "environment": environment or {}, "policy": policy_profile},
        )
        return sess

    def close(self, session_id: str) -> None:
        sess = self._sessions.pop(session_id, None)
        if sess is not None:
            try:
                sess.ctx.emit("session_end", {"status": "closed"})
            except Exception:
                pass

    # -- ExecutionService ----------------------------------------------------
    def start_trace(self, session_id: str, entry: str) -> ExecutionContext:
        sess = self._sessions[session_id]
        ex = TraceExecutor(policy=sess.policy, artifacts=self.artifacts)
        traced = ex.trace_file(entry)
        # Merge traced events into the session log preserving order.
        for item in traced.log.to_list():
            kind = item["kind"]
            if kind in ("session_start", "session_end"):
                continue
            sess.ctx.log.append(
                kind,
                item.get("payload", {}),
                source_location=None,
                artifact_refs=item.get("artifact_refs", []),
            )
        return sess.ctx

    # -- EventService ---------------------------------------------------------
    def subscribe(self, session_id: str, after_seq: int = -1) -> list[Event]:
        return self._sessions[session_id].ctx.log.subscribe(after_seq)

    # -- ArtifactService ------------------------------------------------------
    def put(self, data: bytes, mime: str = "application/octet-stream", **prov: Any) -> str:
        return self.artifacts.put(data, mime, **prov)

    def get(self, ref: str) -> bytes:
        return self.artifacts.get(ref)

    # -- Checkpoint -----------------------------------------------------------
    def checkpoint(self, session_id: str, flavor: str = "replayable") -> Checkpoint:
        sess = self._sessions[session_id]
        return Checkpoint(
            flavor=flavor,
            event_seq=len(sess.ctx.log),
            runtime_id="trace",
            policy_profile=sess.policy.profile,
            artifact_hashes=self.artifacts.list_refs(),
            replayable=(flavor == "replayable"),
        )
