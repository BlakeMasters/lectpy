"""Broker daemon API tests: auth, sessions, trace, jobs, PTY, WS, artifacts.

Spins a real loopback daemon on an ephemeral port (module fixture) and
drives it over HTTP + WebSocket like the shell does. Kernel-backed tests
live in test_jupyter_provider.py.
"""
import asyncio
import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from lecture.broker.server import BrokerServer, ServerConfig

REPO = Path(__file__).resolve().parents[1]
TOKEN = "test-token-abc123"


def api(srv, method, path, body=None, token=TOKEN):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        srv.url + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            return resp.status, json.loads(data or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def api_raw(srv, path, token=TOKEN):
    req = urllib.request.Request(
        srv.url + path, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture(scope="module")
def srv(tmp_path_factory):
    root = tmp_path_factory.mktemp("broker")
    server = BrokerServer(
        ServerConfig(
            port=0,
            token=TOKEN,
            token_path=root / "broker.token",
            artifact_root=root / "artifacts",
            cwd=str(REPO),
        )
    ).start()
    yield server
    server.stop()


@pytest.fixture()
def session(srv):
    code, body = api(srv, "POST", "/v1/sessions", {"policy_profile": "local-trusted"})
    assert code == 200
    sid = body["session_id"]
    yield sid
    api(srv, "DELETE", f"/v1/sessions/{sid}")


def test_health_needs_no_auth_but_publishes_ws_port(srv):
    code, body = api(srv, "GET", "/v1/health", token=None)
    assert code == 200 and body["ok"] is True
    assert isinstance(body["ws_port"], int)


def test_capabilities_lists_providers(srv):
    code, body = api(srv, "GET", "/v1/capabilities")
    assert code == 200
    assert "trace" in body["providers"] and "pty" in body["providers"]
    assert body["pty_backend"] in ("winpty", "posix-pty", "none")


def test_missing_token_is_401(srv):
    code, _ = api(srv, "POST", "/v1/sessions", {}, token=None)
    assert code == 401
    code, _ = api(srv, "POST", "/v1/sessions", {}, token="wrong")
    assert code == 401


def test_token_persisted_to_file(srv):
    assert srv.state.token == TOKEN  # explicit token wins; file still written
    assert Path(srv.config.token_path).exists()


def test_session_trace_and_event_poll(srv, session):
    code, body = api(srv, "POST", f"/v1/sessions/{session}/trace", {"entry": "examples/lecture_01.py"})
    assert code == 200 and body["steps"] > 0
    code, poll = api(srv, "GET", f"/v1/sessions/{session}/events?after_seq=-1")
    assert code == 200 and len(poll["events"]) > body["steps"]
    first = body["events"][0]["seq"]
    code, tail = api(srv, "GET", f"/v1/sessions/{session}/events?after_seq={first}")
    assert code == 200 and all(e["seq"] > first for e in tail["events"])


def test_trace_missing_entry_is_404(srv, session):
    code, _ = api(srv, "POST", f"/v1/sessions/{session}/trace", {"entry": "nope.py"})
    assert code == 404


def test_unknown_session_is_404(srv):
    code, _ = api(srv, "GET", "/v1/sessions/sess_dead/events")
    assert code == 404


def test_static_profile_denies_jobs_and_pty(srv):
    code, body = api(srv, "POST", "/v1/sessions", {"policy_profile": "static"})
    sid = body["session_id"]
    try:
        code, _ = api(srv, "POST", f"/v1/sessions/{sid}/jobs", {"argv": ["python", "--version"]})
        assert code == 403
        code, _ = api(srv, "POST", f"/v1/sessions/{sid}/pty", {})
        assert code == 403
    finally:
        api(srv, "DELETE", f"/v1/sessions/{sid}")


def _wait_job(srv, sid, jid, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        code, job = api(srv, "GET", f"/v1/sessions/{sid}/jobs/{jid}")
        assert code == 200
        if job["status"] != "running":
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish in time")


def test_job_runs_and_reports(srv, session):
    code, body = api(srv, "POST", f"/v1/sessions/{session}/jobs", {"argv": ["python", "--version"]})
    assert code == 200
    job = _wait_job(srv, session, body["job_id"])
    assert job["exit_code"] == 0 and "Python" in job["output"]


def test_job_missing_binary_is_127(srv, session):
    code, body = api(
        srv, "POST", f"/v1/sessions/{session}/jobs", {"argv": ["lectpy-no-such-bin-xyz"]}
    )
    assert code == 200
    job = _wait_job(srv, session, body["job_id"])
    assert job["exit_code"] == 127


def test_job_cancel_terminates_tree(srv, session):
    code, body = api(
        srv,
        "POST",
        f"/v1/sessions/{session}/jobs",
        {"argv": ["python", "-c", "import time; time.sleep(120)"], "timeout": 120},
    )
    assert code == 200
    jid = body["job_id"]
    time.sleep(1.0)  # let the child exec
    code, killed = api(srv, "DELETE", f"/v1/sessions/{session}/jobs/{jid}")
    assert code == 200 and killed["status"] in ("terminated", "timed-out", "done")
    job = _wait_job(srv, session, jid)
    assert job["status"] in ("terminated", "timed-out")
    assert job["exit_code"] != 0


def test_job_output_truncation(srv, session):
    code, body = api(
        srv,
        "POST",
        f"/v1/sessions/{session}/jobs",
        {"argv": ["python", "-c", "print('A' * 3000000)"]},
    )
    assert code == 200
    job = _wait_job(srv, session, body["job_id"])
    assert job["truncated_bytes"] > 0 and "truncated" not in job["output"]
    assert len(job["output"].encode()) <= 1_000_000 + 100


def test_artifacts_roundtrip_and_404(srv):
    blob = base64.b64encode(b"artifact-bytes").decode()
    code, body = api(srv, "PUT", "/v1/artifacts", {"mime": "text/plain", "data_b64": blob})
    assert code == 200 and body["ref"].startswith("sha256:")
    hexpart = body["ref"].split(":", 1)[1]
    status, data = api_raw(srv, f"/v1/artifacts/{hexpart}")
    assert status == 200 and data == b"artifact-bytes"
    status, _ = api_raw(srv, "/v1/artifacts/" + "0" * 64)
    assert status == 404
    status, _ = api_raw(srv, "/v1/artifacts/..%2F..%2Fsecret")
    assert status == 404


def _ws_url(srv, path, token=TOKEN):
    code, health = api(srv, "GET", "/v1/health", token=None)
    ws_base = f"ws://127.0.0.1:{health['ws_port']}"
    sep = "&" if "?" in path else "?"
    return f"{ws_base}{path}{sep}token={token}"


def test_ws_stream_replays_then_pushes(srv, session):
    import websockets

    async def run():
        received = []
        async with websockets.connect(_ws_url(srv, f"/v1/sessions/{session}/stream?after_seq=-1")) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 10))
            assert hello["type"] == "hello"
            # Trace while attached: replay + live push must both arrive.
            code, _ = await asyncio.to_thread(
                api, srv, "POST", f"/v1/sessions/{session}/trace", {"entry": "examples/lecture_01.py"}
            )
            assert code == 200
            deadline = time.time() + 20
            while time.time() < deadline:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
                except TimeoutError:
                    break
                if msg.get("type") == "event":
                    received.append(msg["event"])
                    if msg["event"]["kind"] == "snapshot":
                        break
        return received

    events = asyncio.run(run())
    kinds = [e["kind"] for e in events]
    assert "step" in kinds and "snapshot" in kinds
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)


def test_ws_stream_rejects_bad_token(srv, session):
    import websockets

    async def run():
        try:
            async with websockets.connect(
                _ws_url(srv, f"/v1/sessions/{session}/stream", token="bad")
            ) as ws:
                await asyncio.wait_for(ws.recv(), 5)
                return "open"
        except Exception:
            return "denied"

    assert asyncio.run(run()) == "denied"


needs_pty = pytest.mark.skipif(
    __import__("lecture.broker.pty", fromlist=["detect_backend"]).detect_backend() == "none",
    reason="no PTY backend on this host",
)


@needs_pty
def test_pty_spawn_and_delete(srv, session):
    code, body = api(
        srv,
        "POST",
        f"/v1/sessions/{session}/pty",
        {"argv": ["python", "-c", "import time; time.sleep(60)"], "cols": 80, "rows": 24},
    )
    assert code == 200, body
    assert body["backend"] in ("winpty", "posix-pty")
    assert body["cols"] == 80 and body["rows"] == 24
    pid = body["pty_id"]
    code, _ = api(srv, "DELETE", f"/v1/sessions/{session}/pty/{pid}")
    assert code == 200
    code, _ = api(srv, "DELETE", f"/v1/sessions/{session}/pty/{pid}")
    assert code == 404
    # Default shell spawn path (no argv).
    code, body = api(srv, "POST", f"/v1/sessions/{session}/pty", {})
    assert code == 200
    api(srv, "DELETE", f"/v1/sessions/{session}/pty/{body['pty_id']}")


@needs_pty
def test_ws_pty_attach_receives_output_and_exit(srv, session):
    import websockets

    async def run():
        code, body = await asyncio.to_thread(
            api,
            srv,
            "POST",
            f"/v1/sessions/{session}/pty",
            {"argv": ["python", "-c", "print('pty-ws-hi')"]},
        )
        assert code == 200
        pid = body["pty_id"]
        out = b""
        exited = False
        try:
            async with websockets.connect(_ws_url(srv, f"/v1/ptys/{pid}/attach")) as ws:
                deadline = time.time() + 20
                while time.time() < deadline:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), 8))
                    except TimeoutError:
                        break
                    if msg.get("type") == "output":
                        out += base64.b64decode(msg["data"])
                        if b"pty-ws-hi" in out:
                            pass
                    elif msg.get("type") == "exit":
                        exited = True
                        break
        finally:
            await asyncio.to_thread(api, srv, "DELETE", f"/v1/sessions/{session}/pty/{pid}")
        return out, exited

    out, exited = asyncio.run(run())
    assert b"pty-ws-hi" in out
    assert exited
