"""Jupyter kernel provider: general REPL/cell execution over the kernel protocol.

The trace stepper stays the pedagogical provider; this is the general one.
Kernels are independent processes reached through the versioned Jupyter
messaging protocol (shell / iopub / stdin / control / heartbeat) — never a
bespoke Python RPC. Rich outputs map onto lecture event kinds; image payloads
travel through the artifact store, never eagerly inlined.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

VEGA_MIMES = (
    "application/vnd.vegalite.v5+json",
    "application/vnd.vegalite.v4+json",
    "application/vnd.vegalite.v3+json",
    "application/vnd.vegalite.v2+json",
    "application/vnd.vega.v5+json",
)


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)


def _require_jupyter_client():  # lazy: `import lecture` stays light without it
    try:
        import jupyter_client  # noqa: F401
        from jupyter_client import KernelManager
    except ImportError as e:
        raise RuntimeError(
            "Jupyter provider needs jupyter_client: pip install lectpy[jupyter]"
        ) from e
    return KernelManager


@dataclass
class JupyterKernel:
    id: str = field(default_factory=lambda: f"kernel_{uuid.uuid4().hex[:12]}")
    kernel_name: str = "python3"
    _km: Any = field(default=None, repr=False)
    _kc: Any = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def start(self, timeout: float = 60.0) -> JupyterKernel:
        KernelManager = _require_jupyter_client()
        km = KernelManager(kernel_name=self.kernel_name)
        km.start_kernel()
        kc = km.blocking_client()
        kc.start_channels()
        kc.wait_for_ready(timeout=timeout)
        self._km, self._kc = km, kc
        return self

    def execute(self, code: str, timeout: float = 30.0) -> list[dict[str, Any]]:
        """Run code; return [{kind, payload, artifact_refs, artifact_blobs?}].

        Binary outputs ride alongside as `artifact_blobs: [{mime, data_b64}]`;
        the broker persists them into the CAS store and rewrites refs/srcs.
        """
        if self._kc is None:
            raise RuntimeError("kernel not started")
        with self._lock:
            return self._execute_locked(code, timeout)

    def _execute_locked(self, code: str, timeout: float) -> list[dict[str, Any]]:
        kc = self._kc
        events: list[dict[str, Any]] = []
        streams = {"stdout": [], "stderr": []}
        deadline = time.time() + timeout
        msg_id = kc.execute(code)

        def flush_streams() -> None:
            for name in ("stdout", "stderr"):
                if streams[name]:
                    text = _strip_ansi("".join(streams[name]))
                    streams[name].clear()
                    if text:
                        events.append(
                            {
                                "kind": "terminal",
                                "payload": {"output": text, "stream": name},
                                "artifact_refs": [],
                            }
                        )

        shell_done = False
        shell_error: dict[str, Any] | None = None
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            try:
                msg = kc.get_iopub_msg(timeout=min(1.0, remaining))
            except Exception:
                if shell_done:
                    break
                continue
            mtype = msg["header"]["msg_type"]
            content = msg["content"]
            if mtype == "status" and content.get("execution_state") == "idle":
                # Idle *for our request* once the shell reply arrived.
                if shell_done:
                    break
            elif mtype == "stream":
                streams[content.get("name", "stdout")].append(content.get("text", ""))
            elif mtype in ("display_data", "execute_result"):
                flush_streams()
                events.append(self._rich_output(content))
            elif mtype == "error":
                flush_streams()
                tb = "\n".join(content.get("traceback", []))
                events.append(
                    {
                        "kind": "error",
                        "payload": {
                            "message": f"{content.get('ename', '')}: {content.get('evalue', '')}",
                            "traceback": _strip_ansi(tb)[-4000:],
                        },
                        "artifact_refs": [],
                    }
                )
            # Check the shell channel without blocking the iopub drain.
            try:
                while True:
                    reply = kc.get_shell_msg(timeout=0)
                    if reply["parent_header"].get("msg_id") != msg_id:
                        continue
                    if reply["header"]["msg_type"] == "execute_reply":
                        shell_done = True
                        if reply["content"].get("status") == "error":
                            shell_error = reply["content"]
                    break
            except Exception:
                pass
            if shell_done:
                # One more short drain so trailing output is not lost.
                try:
                    while True:
                        msg2 = kc.get_iopub_msg(timeout=0.2)
                        if (
                            msg2["header"]["msg_type"] == "status"
                            and msg2["content"].get("execution_state") == "idle"
                        ):
                            break
                        c2 = msg2["content"]
                        if msg2["header"]["msg_type"] == "stream":
                            streams[c2.get("name", "stdout")].append(c2.get("text", ""))
                        elif msg2["header"]["msg_type"] in ("display_data", "execute_result"):
                            flush_streams()
                            events.append(self._rich_output(c2))
                except Exception:
                    pass
                break
        else:
            pass
        if time.time() >= deadline and not shell_done:
            try:
                kc.interrupt_kernel()
            except Exception:
                pass
            events.append(
                {
                    "kind": "error",
                    "payload": {"message": f"execution timed out after {timeout}s (interrupted)"},
                    "artifact_refs": [],
                }
            )
        flush_streams()
        if shell_error and not any(e["kind"] == "error" for e in events):
            msg = f"{shell_error.get('ename', '')}: {shell_error.get('evalue', '')}"
            events.append({"kind": "error", "payload": {"message": msg}, "artifact_refs": []})
        return events

    def _rich_output(self, content: dict[str, Any]) -> dict[str, Any]:
        data = content.get("data", {}) or {}
        for mime in VEGA_MIMES:
            if mime in data:
                return {"kind": "plot", "payload": {"spec": data[mime]}, "artifact_refs": []}
        if "image/png" in data:
            return {
                "kind": "image",
                "payload": {"src": "", "alt": "kernel output image"},
                "artifact_refs": [],
                "artifact_blobs": [{"mime": "image/png", "data_b64": data["image/png"]}],
            }
        if "text/html" in data:
            # Withhold unsanitized HTML; show source until the v0.4 sanitizer.
            return {
                "kind": "text",
                "payload": {"markdown": f"```html\n{data['text/html']}\n```"},
                "artifact_refs": [],
            }
        if "application/json" in data:
            import json as _json

            pretty = _json.dumps(data["application/json"], indent=2)
            return {
                "kind": "text",
                "payload": {"markdown": f"```json\n{pretty}\n```"},
                "artifact_refs": [],
            }
        plain = data.get("text/plain", "")
        if isinstance(plain, list):
            plain = "".join(plain)
        return {
            "kind": "text",
            "payload": {"markdown": f"```\n{plain}\n```"},
            "artifact_refs": [],
        }

    def interrupt(self) -> None:
        if self._kc is not None:
            try:
                self._kc.interrupt_kernel()
            except Exception:
                pass

    def shutdown(self) -> None:
        kc, km = self._kc, self._km
        self._kc, self._km = None, None
        if kc is not None:
            try:
                kc.stop_channels()
            except Exception:
                pass
        if km is not None:
            try:
                km.shutdown_kernel(now=True)
            except Exception:
                pass
