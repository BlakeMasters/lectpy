"""Same-origin static serving plus an explicitly enabled local automation bridge."""

from __future__ import annotations

import hmac
import http.server
import json
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from .automation import AutomationService


def automation_handler(root: Path, service: AutomationService):
    token = secrets.token_urlsafe(32)
    netloc = urlsplit(service.base_url).netloc

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def log_message(self, *_args):
            pass

        def _allowed(self):
            origin = self.headers.get("Origin")
            local = not origin or (
                urlsplit(origin).scheme == "http"
                and urlsplit(origin).hostname in ("127.0.0.1", "localhost", "::1")
            )
            return self.headers.get("Host") == netloc and local

        def _json(self, code, value):
            data = json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            if self._allowed() and self.headers.get("Origin"):
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._json(200 if self._allowed() else 403, {})

        def do_GET(self):
            path = urlsplit(self.path).path
            if path.startswith("/_lecture/automation"):
                if not self._allowed():
                    self._json(403, {"error": "local runner only"})
                    return
                if path == "/_lecture/automation":
                    self._json(200, {**service.snapshot(), "token": token})
                    return
                prefix = "/_lecture/automation/captures/"
                key = path[len(prefix) :].removesuffix(".png") if path.startswith(prefix) else ""
                with service.lock:
                    data = service.images.get(key)
                if data:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._json(404, {"error": "capture no longer available"})
                return
            super().do_GET()

        def do_POST(self):
            if urlsplit(self.path).path != "/_lecture/automation":
                self._json(404, {"error": "no such endpoint"})
                return
            provided = self.headers.get("Authorization", "")
            if not self._allowed() or not hmac.compare_digest(provided, f"Bearer {token}"):
                self._json(403, {"error": "local runner authentication required"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("command must contain 1–4096 bytes")
                body = json.loads(self.rfile.read(length))
                result = service.submit(
                    body["id"], body["action"], body["request_id"], body.get("step", 0)
                )
                self._json(202, result)
            except (KeyError, TypeError, ValueError) as exc:
                self._json(400, {"error": str(exc)})

    return Handler
