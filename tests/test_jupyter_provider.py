"""Jupyter provider tests: real kernel, real protocol, mapped events.

Skipped without jupyter_client. Kernel start dominates runtime (~10s), so one
module-scoped kernel serves all cases via the broker REST surface — which
also exercises the kernels/execute/interrupt routes end to end.
"""
import time
import urllib.error
import urllib.request
import json
from pathlib import Path

import pytest

pytest.importorskip("jupyter_client")

from lecture.broker.server import BrokerServer, ServerConfig  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TOKEN = "test-token-jupyter"


def api(srv, method, path, body=None):
    req = urllib.request.Request(
        srv.url + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


@pytest.fixture(scope="module")
def kern(tmp_path_factory):
    root = tmp_path_factory.mktemp("jupyter")
    srv = BrokerServer(
        ServerConfig(port=0, token=TOKEN, artifact_root=root / "artifacts",
                     token_path=root / "broker.token", cwd=str(REPO))
    ).start()
    code, body = api(srv, "POST", "/v1/sessions", {"policy_profile": "local-trusted"})
    assert code == 200
    sid = body["session_id"]
    code, body = api(srv, "POST", f"/v1/sessions/{sid}/kernels", {"kernel": "python3"})
    assert code == 200, body
    yield srv, sid, body["kernel_id"]
    srv.stop()


def _execute(kern, code_text, timeout=30):
    srv, sid, kid = kern
    code, body = api(
        srv, "POST", f"/v1/sessions/{sid}/kernels/{kid}/execute",
        {"code": code_text, "timeout": timeout},
    )
    assert code == 200, body
    return body["events"]


def test_execute_result_maps_to_text(kern):
    events = _execute(kern, "1 + 1")
    texts = [e for e in events if e["kind"] == "text"]
    assert texts and any("2" in (e["payload"].get("markdown", "")) for e in texts)


def test_stream_maps_to_terminal(kern):
    events = _execute(kern, "print('kj-hi')")
    terms = [e for e in events if e["kind"] == "terminal"]
    assert terms and any("kj-hi" in (e["payload"].get("output", "")) for e in terms)


def test_error_maps_to_error_event(kern):
    events = _execute(kern, "1 / 0")
    errors = [e for e in events if e["kind"] == "error"]
    assert errors and any("ZeroDivisionError" in (e["payload"].get("message", "")) for e in errors)


def test_interrupt_route(kern):
    srv, sid, kid = kern
    code, body = api(srv, "POST", f"/v1/sessions/{sid}/kernels/{kid}/interrupt")
    assert code == 200 and body.get("interrupted") is True


def test_unknown_kernel_is_404(kern):
    srv, sid, _ = kern
    code, _ = api(srv, "POST", f"/v1/sessions/{sid}/kernels/kernel_dead/execute", {"code": "1"})
    assert code == 404
