"""ExecutionProvider contracts.

A provider owns its runtime (trace stepper, Jupyter kernel, Deno, process,
WASI, OCI, remote). The microkernel only sees this interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..artifacts import ArtifactStore
from ..context import ExecutionContext
from ..policy import GrantedPolicy


@dataclass
class ProviderCapabilities:
    runtimes: tuple[str, ...]
    supports_interrupt: bool = False
    supports_pty: bool = False
    sandboxed: bool = False


@dataclass
class SessionSpec:
    document: str = ""
    environment: dict[str, Any] = None  # type: ignore[assignment]
    policy_profile: str = "local-trusted"

    def __post_init__(self) -> None:
        if self.environment is None:
            self.environment = {}


@dataclass
class ExecutionSpec:
    entry: str = ""  # e.g. path to lecture .py, or inline code id
    args: tuple[str, ...] = ()
    cwd: str = "."


class ExecutionProvider(Protocol):
    id: str

    async def probe(self) -> ProviderCapabilities: ...
    async def execute(
        self, spec: ExecutionSpec, policy: GrantedPolicy, artifacts: ArtifactStore | None = None
    ) -> ExecutionContext: ...


@dataclass
class TraceProvider:
    """Pedagogical sys.settrace stepper — one provider among many."""

    id: str = "trace"

    async def probe(self) -> ProviderCapabilities:
        return ProviderCapabilities(runtimes=("python-trace",), sandboxed=False)

    async def execute(
        self, spec: ExecutionSpec, policy: GrantedPolicy, artifacts: ArtifactStore | None = None
    ) -> ExecutionContext:
        from ..trace import TraceExecutor

        ex = TraceExecutor(policy=policy, artifacts=artifacts)
        return ex.trace_file(spec.entry)
