"""Loopback broker daemon: one protocol, two local listeners.

REST (JSON) for sessions, trace, jobs, PTY lifecycle, kernels, artifacts;
WebSocket for the ordered event stream and PTY byte frames. Remote
deployments put TLS + stronger isolation in front and speak this same
logical API — the wire model never carries PIDs or host paths.

Auth: bearer token on every route except /v1/health (REST: Authorization
header or ?token=; WS: ?token= since browsers cannot set WS headers).
CORS reflects loopback Origins only. WS Origins outside loopback are
rejected at the handshake.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import queue
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..events import EventLog, new_id
from ..policy import PROFILES, GrantedPolicy, PolicyViolation, default_policy
from ..trace import TraceExecutor
from .auth import check_token, load_or_create_token
from .bus import EventBus
from .jobs import JobManager, NoSuchJob
from .pty import NoPtyBackend, NoSuchPty, PtyManager

VERSION = "0.3.0"
BODY_LIMIT = 8 * 1024 * 1024
ARTIFACT_LIMIT = 50 * 1024 * 1024


@dataclass
class Session:
    id: str
    document: str
    environment: dict[str, Any]
    policy: GrantedPolicy
    log: EventLog
    kernels: dict[str, Any] = field(default_factory=dict)
    created: float = field(default_factory=time.time)


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 7888
    token: str | None = None
    token_path: str | Path = ".lecture/broker.token"
    artifact_root: str | Path = ".lecture/artifacts"
    cwd: str | Path = "."


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class BrokerState:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.token = load_or_create_token(config.token, config.token_path)
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.artifacts = ArtifactStore(config.artifact_root)
        self.jobs = JobManager()
        self.ptys = PtyManager()
        self.bus = EventBus()

    # -- sessions ---------------------------------------------------------
    def open_session(
        self, document: str, environment: dict[str, Any], policy_profile: str
    ) -> Session:
        policy = default_policy(policy_profile)  # ValueError -> 400 in handler
        sid = new_id("sess")
        sess = Session(
            id=sid,
            document=document,
            environment=environment,
            policy=policy,
            log=EventLog(sid, new_id("exec")),
        )
        with self.lock:
            self.sessions[sid] = sess
        self.append(sid, "session_start", {"document": document, "policy": policy_profile})
        return sess

    def get_session(self, sid: str) -> Session:
        with self.lock:
            try:
                return self.sessions[sid]
            except KeyError:
                raise ApiError(404, f"unknown session: {sid}") from None

    def close_session(self, sid: str) -> None:
        with self.lock:
            sess = self.sessions.pop(sid, None)
        if sess is None:
            return
        for kid, kernel in list(sess.kernels.items()):
            try:
                kernel.shutdown()
            except Exception:
                pass
            sess.kernels.pop(kid, None)
        try:
            self.jobs.reap_session(sid)
        except Exception:
            pass
        try:
            self.ptys.reap_session(sid)
        except Exception:
            pass

    def append(
        self,
        sid: str,
        kind: str,
        payload: dict[str, Any],
        artifact_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        sess = self.get_session(sid)
        # Lifecycle events are exempt: a zero-budget profile (static) must
        # still open/close; the budget governs content events.
        if kind not in ("session_start", "session_end"):
            if len(sess.log) >= sess.policy.max_events:
                raise ApiError(429, f"event budget exceeded ({sess.policy.max_events})")
        ev = sess.log.append(kind, payload, artifact_refs=artifact_refs or [])
        item = ev.to_dict()
        self.bus.publish(sid, item)
        return item

    # -- trace ------------------------------------------------------------
    def run_trace(self, sid: str, entry: str) -> dict[str, Any]:
        sess = self.get_session(sid)
        path = Path(entry)
        if not path.is_absolute():
            path = Path(self.config.cwd) / path
        if not path.exists():
            raise ApiError(404, f"no such entry: {entry}")
        ex = TraceExecutor(policy=sess.policy, artifacts=self.artifacts)
        ctx = ex.trace_file(path)
        shipped: list[dict[str, Any]] = []
        for item in ctx.log.to_list():
            if item["kind"] in ("session_start", "session_end"):
                continue
            shipped.append(
                self.append(
                    sid, item["kind"], item.get("payload", {}), item.get("artifact_refs", [])
                )
            )
        steps = sum(1 for e in shipped if e["kind"] == "step")
        self.append(sid, "snapshot", {"trace": str(path), "steps": steps})
        return {"events": shipped, "steps": steps}

    # -- jupyter blobs ----------------------------------------------------
    def persist_blobs(self, blobs: list[dict[str, Any]]) -> list[str]:
        refs = []
        for b in blobs:
            try:
                raw = base64.b64decode(b["data_b64"])
            except (KeyError, binascii.Error) as e:
                raise ApiError(400, f"bad artifact blob: {e}") from e
            if len(raw) > ARTIFACT_LIMIT:
                raise ApiError(413, "artifact blob too large")
            refs.append(self.artifacts.put(raw, b.get("mime", "application/octet-stream")))
        return refs


def _loopback_host(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "[::1]", "::1")


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True  # non-browser client
    try:
        parts = urllib.parse.urlparse(origin)
        return _loopback_host((parts.hostname or "").lower())
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    state: BrokerState  # set by BrokerServer
    server_version = "lectured/0.3"

    # -- plumbing ---------------------------------------------------------
    def log_message(self, *args: Any) -> None:  # quiet; broker has no access log in v0.3
        pass

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin and _origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")

    def _send_json(self, code: int, obj: Any, raw: bytes | None = None) -> None:
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _query(self) -> dict[str, str]:
        parts = urllib.parse.urlparse(self.path)
        return {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}

    def _authed(self) -> bool:
        if self.path.startswith("/v1/health"):
            return True
        auth = self.headers.get("Authorization", "")
        bearer = auth[7:] if auth.startswith("Bearer ") else None
        return check_token(self.state.token, bearer or self._query().get("token"))

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > BODY_LIMIT:
            raise ApiError(413, "request body too large")
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            obj = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ApiError(400, f"invalid JSON: {e}") from e
        return obj if isinstance(obj, dict) else {}

    # -- routing ----------------------------------------------------------
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        try:
            if not self._authed():
                return self._fail(401, "missing or invalid bearer token")
            parts = urllib.parse.urlparse(self.path)
            segs = [s for s in parts.path.split("/") if s]
            if segs == ["v1", "health"]:
                ws_port = getattr(self.server, "ws_port", None)
                return self._send_json(200, {"ok": True, "version": VERSION, "ws_port": ws_port})
            if segs == ["v1", "capabilities"]:
                from .pty import detect_backend

                try:
                    from .jupyter_provider import _require_jupyter_client

                    _require_jupyter_client()
                    jupyter = True
                except RuntimeError:
                    jupyter = False
                return self._send_json(
                    200,
                    {
                        "providers": ["trace", "process", "pty"] + (["jupyter"] if jupyter else []),
                        "pty_backend": detect_backend(),
                        "jupyter": jupyter,
                        "profiles": list(PROFILES),
                    },
                )
            if len(segs) == 4 and segs[:2] == ["v1", "sessions"] and segs[3] == "events":
                sess = self.state.get_session(segs[2])
                after = int(self._query().get("after_seq", "-1"))
                return self._send_json(
                    200, {"events": [e.to_dict() for e in sess.log.subscribe(after)]}
                )
            if len(segs) == 5 and segs[:2] == ["v1", "sessions"] and segs[3] == "jobs":
                sess = self.state.get_session(segs[2])
                job = self.state.jobs.get(segs[4])
                if job.session_id != sess.id:
                    raise ApiError(404, "unknown job")
                return self._send_json(200, job.snapshot(sess.policy.max_output_bytes))
            if len(segs) == 3 and segs[:2] == ["v1", "artifacts"]:
                try:
                    data = self.state.artifacts.get("sha256:" + segs[2])
                except (KeyError, ValueError):
                    raise ApiError(404, "unknown artifact") from None
                meta = self.state.artifacts.meta("sha256:" + segs[2])
                self.send_response(200)
                self.send_header("Content-Type", meta.mime if meta else "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self._cors()
                self.end_headers()
                return self.wfile.write(data)
            return self._fail(404, "unknown route")
        except ApiError as e:
            return self._fail(e.status, e.message)
        except (NoSuchJob, KeyError):
            return self._fail(404, "unknown job")
        except Exception as e:  # never leak tracebacks to the browser
            return self._fail(500, f"internal error: {type(e).__name__}")

    def do_POST(self) -> None:
        try:
            if not self._authed():
                return self._fail(401, "missing or invalid bearer token")
            segs = [s for s in urllib.parse.urlparse(self.path).path.split("/") if s]
            body = self._read_json()
            if segs == ["v1", "sessions"]:
                try:
                    sess = self.state.open_session(
                        str(body.get("document", "")),
                        dict(body.get("environment", {})),
                        str(body.get("policy_profile", "local-trusted")),
                    )
                except ValueError as e:
                    raise ApiError(400, str(e)) from e
                return self._send_json(200, {"session_id": sess.id})
            if len(segs) == 4 and segs[:2] == ["v1", "sessions"] and segs[3] == "trace":
                if "entry" not in body:
                    raise ApiError(400, "missing 'entry'")
                return self._send_json(200, self.state.run_trace(segs[2], str(body["entry"])))
            if len(segs) == 4 and segs[:2] == ["v1", "sessions"] and segs[3] == "jobs":
                sess = self.state.get_session(segs[2])
                if "argv" not in body or not isinstance(body["argv"], list):
                    raise ApiError(400, "'argv' must be a non-empty list")
                try:
                    job = self.state.jobs.start(
                        sess.id,
                        [str(a) for a in body["argv"]],
                        sess.policy,
                        cwd=str(body.get("cwd", ".")),
                        env=body.get("env"),
                        timeout=body.get("timeout"),
                    )
                except PolicyViolation as e:
                    raise ApiError(403, str(e)) from e
                except ValueError as e:
                    raise ApiError(400, str(e)) from e
                self.state.append(sess.id, "terminal", {"argv": job.argv, "job_id": job.id})
                return self._send_json(200, {"job_id": job.id})
            if len(segs) == 4 and segs[:2] == ["v1", "sessions"] and segs[3] == "pty":
                sess = self.state.get_session(segs[2])
                try:
                    pty = self.state.ptys.spawn(
                        sess.id,
                        sess.policy,
                        argv=body.get("argv"),
                        cols=int(body.get("cols", 100)),
                        rows=int(body.get("rows", 30)),
                        cwd=str(body.get("cwd", ".")),
                        env=body.get("env"),
                    )
                except PolicyViolation as e:
                    raise ApiError(403, str(e)) from e
                except NoPtyBackend as e:
                    raise ApiError(501, str(e)) from e
                except ValueError as e:
                    raise ApiError(400, str(e)) from e
                self.state.append(
                    sess.id, "terminal", {"argv": pty.argv, "pty_id": pty.id, "mode": "live"}
                )
                return self._send_json(
                    200,
                    {"pty_id": pty.id, "backend": pty.backend, "cols": pty.cols, "rows": pty.rows},
                )
            if len(segs) == 4 and segs[:2] == ["v1", "sessions"] and segs[3] == "kernels":
                from .jupyter_provider import JupyterKernel

                sess = self.state.get_session(segs[2])
                kernel = JupyterKernel(kernel_name=str(body.get("kernel", "python3")))
                try:
                    kernel.start(timeout=float(body.get("timeout", 60)))
                except RuntimeError as e:
                    raise ApiError(501, str(e)) from e
                except Exception as e:
                    raise ApiError(500, f"kernel start failed: {e}") from e
                with self.state.lock:
                    sess.kernels[kernel.id] = kernel
                return self._send_json(200, {"kernel_id": kernel.id})
            if (
                len(segs) == 6
                and segs[:2] == ["v1", "sessions"]
                and segs[3] == "kernels"
                and segs[5] == "execute"
            ):
                sess = self.state.get_session(segs[2])
                with self.state.lock:
                    kernel = sess.kernels.get(segs[4])
                if kernel is None:
                    raise ApiError(404, "unknown kernel")
                if "code" not in body:
                    raise ApiError(400, "missing 'code'")
                raw_events = kernel.execute(str(body["code"]), float(body.get("timeout", 30)))
                shipped = []
                for e in raw_events:
                    refs = list(e.get("artifact_refs", []))
                    for blob in e.pop("artifact_blobs", []):
                        refs.append(
                            self.state.artifacts.put(
                                base64.b64decode(blob["data_b64"]), blob.get("mime", "")
                            )
                        )
                        if e["kind"] == "image" and not e["payload"].get("src"):
                            e["payload"]["src"] = "/v1/artifacts/" + refs[-1].split(":", 1)[1]
                    shipped.append(self.state.append(sess.id, e["kind"], e["payload"], refs))
                return self._send_json(200, {"events": shipped})
            if (
                len(segs) == 6
                and segs[:2] == ["v1", "sessions"]
                and segs[3] == "kernels"
                and segs[5] == "interrupt"
            ):
                sess = self.state.get_session(segs[2])
                with self.state.lock:
                    kernel = sess.kernels.get(segs[4])
                if kernel is None:
                    raise ApiError(404, "unknown kernel")
                kernel.interrupt()
                return self._send_json(200, {"interrupted": True})
            if segs == ["v1", "artifacts"]:
                try:
                    raw = base64.b64decode(body.get("data_b64", ""))
                except (binascii.Error, ValueError, TypeError) as e:
                    raise ApiError(400, f"bad data_b64: {e}") from e
                if len(raw) > ARTIFACT_LIMIT:
                    raise ApiError(413, "artifact too large")
                ref = self.state.artifacts.put(
                    raw,
                    str(body.get("mime", "application/octet-stream")),
                    source_url=str(body.get("source_url", "")),
                    license=str(body.get("license", "")),
                    attribution=str(body.get("attribution", "")),
                )
                return self._send_json(200, {"ref": ref})
            return self._fail(404, "unknown route")
        except ApiError as e:
            return self._fail(e.status, e.message)
        except (NoSuchJob, NoSuchPty, KeyError):
            return self._fail(404, "unknown target")
        except PolicyViolation as e:
            return self._fail(403, str(e))
        except Exception as e:
            return self._fail(500, f"internal error: {type(e).__name__}")

    def do_PUT(self) -> None:
        # Artifacts accept PUT as an alias for POST /v1/artifacts.
        if urllib.parse.urlparse(self.path).path.rstrip("/") == "/v1/artifacts":
            return self.do_POST()
        if not self._authed():
            return self._fail(401, "missing or invalid bearer token")
        return self._fail(404, "unknown route")

    def do_DELETE(self) -> None:
        try:
            if not self._authed():
                return self._fail(401, "missing or invalid bearer token")
            segs = [s for s in urllib.parse.urlparse(self.path).path.split("/") if s]
            if len(segs) == 3 and segs[:2] == ["v1", "sessions"]:
                self.state.close_session(segs[2])
                return self._send_json(200, {"closed": True})
            if len(segs) == 5 and segs[:2] == ["v1", "sessions"] and segs[3] == "jobs":
                sess = self.state.get_session(segs[2])
                job = self.state.jobs.get(segs[4])
                if job.session_id != sess.id:
                    raise ApiError(404, "unknown job")
                job = self.state.jobs.terminate(segs[4])
                return self._send_json(200, job.snapshot(sess.policy.max_output_bytes))
            if len(segs) == 5 and segs[:2] == ["v1", "sessions"] and segs[3] == "pty":
                sess = self.state.get_session(segs[2])
                try:
                    pty = self.state.ptys.get(segs[4])
                except NoSuchPty as e:
                    raise ApiError(404, "unknown pty") from e
                if pty.session_id != sess.id:
                    raise ApiError(404, "unknown pty")
                self.state.ptys.kill(segs[4])
                self.state.ptys.remove(segs[4])
                return self._send_json(200, {"killed": True})
            if len(segs) == 5 and segs[:2] == ["v1", "sessions"] and segs[3] == "kernels":
                sess = self.state.get_session(segs[2])
                with self.state.lock:
                    kernel = sess.kernels.pop(segs[4], None)
                if kernel is None:
                    raise ApiError(404, "unknown kernel")
                kernel.shutdown()
                return self._send_json(200, {"shutdown": True})
            return self._fail(404, "unknown route")
        except ApiError as e:
            return self._fail(e.status, e.message)
        except (NoSuchJob, NoSuchPty, KeyError):
            return self._fail(404, "unknown target")
        except Exception as e:
            return self._fail(500, f"internal error: {type(e).__name__}")


# -- WebSocket ---------------------------------------------------------------


def _ws_target(request_path: str) -> tuple[str, dict[str, str]]:
    parts = urllib.parse.urlparse(request_path)
    query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
    return parts.path, query


async def _ws_stream_handler(ws: Any, state: BrokerState) -> None:
    import websockets

    path, query = _ws_target(ws.request.path)
    try:
        if not _origin_allowed(ws.request.headers.get("Origin")):
            await ws.close(4403, "origin denied")
            return
        if not check_token(state.token, query.get("token")):
            await ws.close(4401, "unauthorized")
            return
        segs = [s for s in path.split("/") if s]
        if len(segs) != 4 or segs[:2] != ["v1", "sessions"] or segs[3] != "stream":
            await ws.close(4404, "unknown route")
            return
        try:
            sess = state.get_session(segs[2])
        except ApiError:
            await ws.close(4404, "unknown session")
            return
        try:
            after = int(query.get("after_seq", "-1"))
        except ValueError:
            after = -1
        await ws.send(json.dumps({"type": "hello", "session_id": sess.id}))
        for e in sess.log.subscribe(after):
            await ws.send(json.dumps({"type": "event", "event": e.to_dict()}))
            after = e.seq
        sub = state.bus.subscribe(sess.id)
        try:
            while True:
                try:
                    item = await asyncio.to_thread(sub.get, True, 15.0)
                except queue.Empty:
                    try:
                        await ws.ping()
                    except websockets.exceptions.ConnectionClosed:
                        break
                    continue
                try:
                    await ws.send(json.dumps({"type": "event", "event": item}))
                except websockets.exceptions.ConnectionClosed:
                    break
        finally:
            state.bus.unsubscribe(sess.id, sub)
    except Exception:
        try:
            await ws.close(4411, "handler error")
        except Exception:
            pass


async def _ws_pty_handler(ws: Any, state: BrokerState) -> None:
    import websockets

    path, query = _ws_target(ws.request.path)
    try:
        if not _origin_allowed(ws.request.headers.get("Origin")):
            await ws.close(4403, "origin denied")
            return
        if not check_token(state.token, query.get("token")):
            await ws.close(4401, "unauthorized")
            return
        segs = [s for s in path.split("/") if s]
        if len(segs) != 4 or segs[:2] != ["v1", "ptys"] or segs[3] != "attach":
            await ws.close(4404, "unknown route")
            return
        try:
            pty = state.ptys.get(segs[2])
        except NoSuchPty:
            await ws.close(4404, "unknown pty")
            return
        history = state.ptys.history(pty.id)
        if history:
            await ws.send(
                json.dumps(
                    {"type": "output", "data": base64.b64encode(history).decode(), "replay": True}
                )
            )
        if not pty.alive:
            await ws.send(json.dumps({"type": "exit", "code": pty.exit_code}))
            await ws.close(1000, "pty exited")
            return
        sub = state.ptys.attach(pty.id)

        async def pump_out() -> None:
            # Loop, never recurse: an idle PTY ticks every 15s for hours.
            while True:
                try:
                    chunk = await asyncio.to_thread(sub.get, True, 15.0)
                except queue.Empty:
                    try:
                        await ws.ping()
                    except websockets.exceptions.ConnectionClosed:
                        return
                    continue
                if chunk is None:  # EOF sentinel
                    try:
                        await ws.send(json.dumps({"type": "exit", "code": pty.exit_code}))
                        await ws.close(1000, "pty exited")
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    return
                try:
                    await ws.send(
                        json.dumps({"type": "output", "data": base64.b64encode(chunk).decode()})
                    )
                except websockets.exceptions.ConnectionClosed:
                    return

        pump = asyncio.ensure_future(pump_out())
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                mtype = msg.get("type")
                if mtype == "input" and isinstance(msg.get("data"), str):
                    try:
                        state.ptys.write(pty.id, base64.b64decode(msg["data"]))
                    except (binascii.Error, NoSuchPty, ValueError):
                        pass
                elif mtype == "resize":
                    try:
                        state.ptys.resize(
                            pty.id, int(msg.get("cols", 100)), int(msg.get("rows", 30))
                        )
                    except (ValueError, NoSuchPty):
                        pass
                elif mtype == "kill":
                    try:
                        state.ptys.kill(pty.id)
                    except NoSuchPty:
                        pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            pump.cancel()
            state.ptys.detach(pty.id, sub)
    except Exception:
        try:
            await ws.close(4411, "handler error")
        except Exception:
            pass


def _ws_main_handler(state: BrokerState):  # factory closes over state
    async def handle(ws: Any) -> None:
        path = urllib.parse.urlparse(ws.request.path).path
        segs = [s for s in path.split("/") if s]
        if len(segs) == 4 and segs[:2] == ["v1", "sessions"] and segs[3] == "stream":
            await _ws_stream_handler(ws, state)
        elif len(segs) == 4 and segs[:2] == ["v1", "ptys"] and segs[3] == "attach":
            await _ws_pty_handler(ws, state)
        else:
            try:
                await ws.close(4404, "unknown route")
            except Exception:
                pass

    return handle


# -- lifecycle -----------------------------------------------------------------


class BrokerServer:
    """Owns the REST listener, the WS listener, and all child runtimes."""

    def __init__(self, config: ServerConfig | None = None) -> None:
        self.config = config or ServerConfig()
        self.state = BrokerState(self.config)
        handler = type("BoundHandler", (Handler,), {"state": self.state})
        self.httpd = ThreadingHTTPServer((self.config.host, self.config.port), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.ws_port: int | None = None
        self._ws_server: Any = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._ws_ready = threading.Event()
        self._ws_thread = threading.Thread(target=self._run_ws, daemon=True)
        self._http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://{self.config.host}:{self.port}"

    def start(self) -> BrokerServer:
        self._http_thread.start()
        self._ws_thread.start()
        if not self._ws_ready.wait(timeout=15):
            raise RuntimeError("WS listener failed to start")
        self.httpd.ws_port = self.ws_port  # type: ignore[attr-defined]
        return self

    def _run_ws(self) -> None:
        from websockets.asyncio.server import serve

        async def main() -> None:
            async with serve(
                _ws_main_handler(self.state),
                self.config.host,
                0,  # ephemeral loopback port; published via /v1/health
                ping_interval=20,
                max_size=4 * 1024 * 1024,
            ) as server:
                self._ws_server = server
                sockets = getattr(server, "sockets", None) or []
                if sockets:
                    self.ws_port = sockets[0].getsockname()[1]
                self._ws_ready.set()
                await server.serve_forever()

        try:
            asyncio.run(main())
        except RuntimeError:
            self._ws_ready.set()

    def stop(self) -> None:
        try:
            self.httpd.shutdown()
        except Exception:
            pass
        try:
            self.httpd.server_close()
        except Exception:
            pass
        with self.state.lock:
            for sid in list(self.state.sessions):
                try:
                    self.state.close_session(sid)
                except Exception:
                    pass
