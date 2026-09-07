"""Loopback broker auth: bearer token, file-persisted with tight perms.

The browser cannot set Authorization headers on WebSocket handshakes, so WS
routes also accept `?token=`. Tokens in URLs can leak into history/logs —
acceptable for loopback development (the default bind), never for remote
deployments, which must terminate TLS in front and rotate tokens.
"""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

TOKEN_ENV = "LECTPY_TOKEN"
DEFAULT_TOKEN_PATH = ".lecture/broker.token"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def load_or_create_token(explicit: str | None = None, path: str | Path = DEFAULT_TOKEN_PATH) -> str:
    if explicit:
        return explicit
    env = os.environ.get(TOKEN_ENV)
    if env:
        return env
    p = Path(path)
    if p.exists():
        saved = p.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    token = new_token()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(token, encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass  # Windows ACLs: file lives in the user's profile by default
    return token


def check_token(expected: str, provided: str | None) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(expected, provided)
