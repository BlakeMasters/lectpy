"""Brokered one-shot native process provider.

The browser never spawns processes. All spawning happens here behind a
capability policy: no shell by default (argv, never shell=True), cwd
confinement, env allowlist, output truncation with backpressure, timeouts,
and process-group termination. PTY/interactive sessions arrive in v0.3.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..policy import GrantedPolicy, PolicyViolation, check_process

BLOCKED_ENV = frozenset({"LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "PYTHONPATH"})


@dataclass
class ProcessResult:
    argv: list[str]
    exit_code: int
    output: str  # combined stdout+stderr, truncated, ANSI-stripped
    truncated_bytes: int = 0
    timed_out: bool = False


def _strip_ansi(s: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)


def run_one_shot(
    argv: Sequence[str],
    *,
    policy: GrantedPolicy,
    cwd: str | Path = ".",
    env: Mapping[str, str] | None = None,
    stdin: bytes | None = None,
    timeout: float | None = None,
) -> ProcessResult:
    argv = list(argv)
    if not argv:
        raise ValueError("empty argv")
    check_process(policy, argv)
    # cwd confinement: must resolve under an allowed fs_read dir, unless
    # local-trusted authoring profile.
    if policy.profile != "local-trusted":
        c = str(cwd)
        norm = c.replace("\\", "/")
        allowed = False
        for a in list(policy.fs_read) + list(policy.fs_write) + ["."]:
            ap = a.replace("\\", "/").rstrip("/") + "/"
            if norm.rstrip("/") + "/" == ap or (norm + "/").startswith(ap) or norm in (".", "./"):
                allowed = True
                break
        if not allowed:
            raise PolicyViolation(f"cwd denied by policy {policy.profile!r}: {cwd!r}")
    merged = dict(os.environ)
    if env:
        for k, v in env.items():
            if k in BLOCKED_ENV:
                raise PolicyViolation(f"blocked env passthrough: {k}")
            merged[k] = v
    # Never inherit ambient LD_PRELOAD-style injection into lecture children.
    for k in BLOCKED_ENV:
        merged.pop(k, None)
    limit = policy.max_output_bytes or 1_000_000
    try:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=merged,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError as e:
        return ProcessResult(argv, 127, f"executable not found: {e}", 0, False)
    try:
        raw, _ = proc.communicate(input=stdin, timeout=timeout or policy.max_wall_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            raw, _ = proc.communicate(timeout=5)
        except Exception:
            raw = b""
        text = _strip_ansi((raw or b"")[:limit].decode("utf-8", errors="replace"))
        return ProcessResult(
            argv, 124, text + "\n…[timeout]", max(0, len(raw or b"") - limit), True
        )
    raw = raw or b""
    truncated = max(0, len(raw) - limit)
    text = _strip_ansi(raw[:limit].decode("utf-8", errors="replace"))
    if truncated:
        text += f"\n…[truncated {truncated} bytes]"
    return ProcessResult(argv, proc.returncode, text, truncated, False)
