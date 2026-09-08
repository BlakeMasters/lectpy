"""Content-addressed artifact store.

Large data is never inlined in the event log. Events carry `sha256:<hex>`
handles plus small previews; the inspector/viewer fetches bytes lazily.
Provenance (source URL, license, retrieval date, hash) travels with each blob
so cached educational assets are redistributable only when licensed as such.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ArtifactMeta:
    hash: str  # "sha256:<hex>"
    bytes: int
    mime: str
    created: float
    source_url: str = ""
    license: str = ""
    attribution: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ArtifactStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._index: dict[str, dict] = {}
        self._lock = threading.RLock()
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._index = {}

    def _save_index(self) -> None:
        # One store instance owns a writer; readers never see half-written JSON.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self.root, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(self._index, stream, indent=2)
        try:
            os.replace(temporary, self._index_path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def put(
        self,
        data: bytes,
        mime: str = "application/octet-stream",
        *,
        source_url: str = "",
        license: str = "",
        attribution: str = "",
    ) -> str:
        ref = self.hash_bytes(data)
        with self._lock:
            dest = self.path(ref, require_exists=False)
            if not dest.exists():
                dest.write_bytes(data)
            self._record(ref, len(data), mime, source_url, license, attribution)
        return ref

    def _record(
        self,
        ref: str,
        size: int,
        mime: str,
        source_url: str = "",
        license: str = "",
        attribution: str = "",
    ) -> None:
        previous = self._index.get(ref, {})
        meta = ArtifactMeta(
            hash=ref,
            bytes=size,
            mime=(previous.get("mime", mime) if mime == "application/octet-stream" else mime),
            created=previous.get("created", time.time()),
            source_url=source_url or previous.get("source_url", ""),
            license=license or previous.get("license", ""),
            attribution=attribution or previous.get("attribution", ""),
        )
        self._index[ref] = meta.to_dict()
        self._save_index()

    def put_file(self, source: str | Path, mime: str = "application/octet-stream") -> str:
        """Capture a file in bounded chunks, including files too large for RAM."""
        digest = hashlib.sha256()
        size = 0
        temporary = None
        try:
            with Path(source).open("rb") as source_stream:
                with tempfile.NamedTemporaryFile(dir=self.blobs, delete=False) as stream:
                    temporary = Path(stream.name)
                    while chunk := source_stream.read(1024 * 1024):
                        digest.update(chunk)
                        stream.write(chunk)
                        size += len(chunk)
            ref = "sha256:" + digest.hexdigest()
            with self._lock:
                dest = self.path(ref, require_exists=False)
                if not dest.exists():
                    os.replace(temporary, dest)
                self._record(ref, size, mime)
            return ref
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def copy_to(self, ref: str, destination: str | Path) -> None:
        """Copy without loading the entire asset into Python memory."""
        shutil.copyfile(self.path(ref), destination)

    def path(self, ref: str, *, require_exists: bool = True) -> Path:
        hexpart = ref.removeprefix("sha256:")
        # Guard against path traversal: only hex digests address blobs.
        if not all(c in "0123456789abcdef" for c in hexpart) or len(hexpart) != 64:
            raise ValueError(f"invalid artifact ref: {ref!r}")
        path = self.blobs / hexpart
        if require_exists and not path.is_file():
            raise KeyError(f"unknown artifact: {ref}")
        return path

    def get(self, ref: str) -> bytes:
        return self.path(ref).read_bytes()

    def meta(self, ref: str) -> ArtifactMeta | None:
        d = self._index.get(ref)
        if not d:
            return None
        return ArtifactMeta(**d)

    def exists(self, ref: str) -> bool:
        return self.path(ref, require_exists=False).is_file()

    def list_refs(self) -> list[str]:
        return sorted(self._index.keys())
