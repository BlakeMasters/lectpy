"""Lecture IR, manifest, and checkpoint descriptors."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORMAT_VERSION = 1


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class LectureManifest:
    format_version: int = FORMAT_VERSION
    title: str = "Untitled lecture"
    source_file: str = ""
    source_sha256: str = ""
    created: float = field(default_factory=time.time)
    runtime: str = "trace"
    policy_profile: str = "local-trusted"
    plugin_ids: list[str] = field(default_factory=list)
    view: str | None = None

    def to_dict(self) -> dict:
        result = asdict(self)
        if self.view is None:
            result.pop("view")
        return result

    @classmethod
    def from_dict(cls, d: dict) -> LectureManifest:
        return cls(
            format_version=int(d.get("format_version", FORMAT_VERSION)),
            title=str(d.get("title", "Untitled lecture")),
            source_file=str(d.get("source_file", "")),
            source_sha256=str(d.get("source_sha256", "")),
            created=float(d.get("created", 0.0)),
            runtime=str(d.get("runtime", "trace")),
            policy_profile=str(d.get("policy_profile", "local-trusted")),
            plugin_ids=list(d.get("plugin_ids", [])),
            view=d.get("view"),
        )


@dataclass
class Checkpoint:
    """Reproducibility descriptor. Three flavors (see ARCHITECTURE.md):

    - replayable: re-running the event log reproduces presentation
    - runtime-native: runtime-specific snapshot (e.g. kernel pickle)
    - recorded: static presentation snapshot only
    """

    flavor: str  # "replayable" | "runtime-native" | "recorded"
    source_sha256: str = ""
    ir_version: int = FORMAT_VERSION
    event_seq: int = 0
    environment_digest: str = ""
    runtime_id: str = "trace"
    plugin_ids: list[str] = field(default_factory=list)
    policy_profile: str = "local-trusted"
    artifact_hashes: list[str] = field(default_factory=list)
    seeds: dict = field(default_factory=dict)
    replayable: bool = True
    side_effects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Checkpoint:
        return cls(
            flavor=str(d.get("flavor", "replayable")),
            source_sha256=str(d.get("source_sha256", "")),
            ir_version=int(d.get("ir_version", FORMAT_VERSION)),
            event_seq=int(d.get("event_seq", 0)),
            environment_digest=str(d.get("environment_digest", "")),
            runtime_id=str(d.get("runtime_id", "trace")),
            plugin_ids=list(d.get("plugin_ids", [])),
            policy_profile=str(d.get("policy_profile", "local-trusted")),
            artifact_hashes=list(d.get("artifact_hashes", [])),
            seeds=dict(d.get("seeds", {})),
            replayable=bool(d.get("replayable", True)),
            side_effects=list(d.get("side_effects", [])),
        )
