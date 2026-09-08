"""Lazy, standard-library asset capture and portable bundle resource mapping."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore
from .context import require_current

ARTIFACT_URI = re.compile(r"^artifact:(sha256:[0-9a-f]{64})$")
LEGACY_URI = re.compile(r"^/v1/artifacts/([0-9a-f]{64})$")
EXTENSIONS = {
    "image/svg+xml": ".svg",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "application/json": ".json",
}


def artifact_ref(value: str) -> str | None:
    match = ARTIFACT_URI.fullmatch(value)
    if match:
        return match[1]
    legacy = LEGACY_URI.fullmatch(value)
    return "sha256:" + legacy[1] if legacy else None


def capture_asset(source: str | Path | bytes, *, mime: str | None = None) -> str:
    """Capture local bytes, or retain an explicit browser URL without fetching it."""
    ctx = require_current()
    if isinstance(source, str):
        if artifact_ref(source):
            return "artifact:" + artifact_ref(source)  # type: ignore[operator]
        if source.startswith(("https://", "http://", "data:", "blob:", "//")):
            return source
        if source.startswith("artifact:"):
            raise ValueError("invalid artifact URI")
    if isinstance(source, bytes):
        if not mime:
            raise ValueError("byte assets require mime=, e.g. mime='image/png'")
    elif isinstance(source, (str, Path)):
        path = Path(source)
        if not path.is_absolute():
            base = Path(ctx.source_file).resolve().parent if ctx.source_file else Path.cwd()
            path = base / path
        if not path.is_file():
            raise FileNotFoundError(f"asset file not found: {path}")
        mime = mime or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    else:
        raise TypeError("asset source must be a path, URL, or bytes")
    if ctx.artifacts is None:
        base = Path(ctx.source_file).resolve().parent if ctx.source_file else Path.cwd()
        ctx.artifacts = ArtifactStore(base / ".lecture" / "artifacts")
    ref = (
        ctx.artifacts.put(source, mime)
        if isinstance(source, bytes)
        else ctx.artifacts.put_file(path, mime)
    )
    return "artifact:" + ref


def collect_refs(value: Any) -> set[str]:
    if isinstance(value, str):
        ref = artifact_ref(value)
        return {ref} if ref else set()
    if isinstance(value, dict):
        return set().union(*(collect_refs(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(collect_refs(v) for v in value))
    return set()


def rewrite_resources(value: Any, resources: dict[str, dict]) -> Any:
    """Return fresh containers so export never mutates the execution's log."""
    if isinstance(value, str):
        ref = artifact_ref(value)
        return resources[ref]["path"] if ref in resources else value
    if isinstance(value, dict):
        return {key: rewrite_resources(item, resources) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_resources(item, resources) for item in value]
    return value
