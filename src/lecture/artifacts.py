"""Content-addressed artifact store.

Large data is never inlined in the event log. Events carry `sha256:<hex>`
handles plus small previews; the inspector/viewer fetches bytes lazily.
Provenance (source URL, license, retrieval date, hash) travels with each blob
so cached educational assets are redistributable only when licensed as such.
"""

from __future__ import annotations

import hashlib
import json
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
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._index = {}

    def _save_index(self) -> None:
        self._index_path.write_text(json.dumps(self._index, indent=2), encoding="utf-8")

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
        hexpart = ref.split(":", 1)[1]
        dest = self.blobs / hexpart
        if not dest.exists():
            dest.write_bytes(data)
        meta = ArtifactMeta(
            hash=ref,
            bytes=len(data),
            mime=mime,
            created=time.time(),
            source_url=source_url,
            license=license,
            attribution=attribution,
        )
        self._index[ref] = meta.to_dict()
        self._save_index()
        return ref

    def get(self, ref: str) -> bytes:
        hexpart = ref.split(":", 1)[1] if ":" in ref else ref
        # Guard against path traversal: only hex digests address blobs.
        if not all(c in "0123456789abcdef" for c in hexpart) or len(hexpart) != 64:
            raise ValueError(f"invalid artifact ref: {ref!r}")
        path = self.blobs / hexpart
        if not path.exists():
            raise KeyError(f"unknown artifact: {ref}")
        return path.read_bytes()

    def meta(self, ref: str) -> ArtifactMeta | None:
        d = self._index.get(ref)
        if not d:
            return None
        return ArtifactMeta(**d)

    def exists(self, ref: str) -> bool:
        hexpart = ref.split(":", 1)[1] if ":" in ref else ref
        return (self.blobs / hexpart).exists()

    def list_refs(self) -> list[str]:
        return sorted(self._index.keys())
