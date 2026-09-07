"""Cancellable one-shot native processes behind the capability broker.

The browser never spawns. Every spawn is policy-gated (argv-only, no shell),
cwd-confined, env-filtered, output-capped with truncation accounting, and
wall-time bounded. DELETE terminates the whole process group (POSIX killpg /
Windows process group), never just the direct child.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..policy import GrantedPolicy, PolicyViolation, check_process
from ..providers.process import BLOCKED_ENV

_TERMINATE_GRACE = 3.0


def check_cwd(policy: GrantedPolicy, cwd: str) -> None:
    if policy.profile == "local-trusted":
        return
    norm = str(cwd).replace("\\", "/")
    candidates = list(policy.fs_read) + list(policy.fs_write) + ["."]
    for allowed in candidates:
        a = allowed.replace("\\", "/").rstrip("/") + "/"
        if norm.rstrip("/") + "/" == a or (norm + "/").startswith(a) or norm in (".", "./"):
            return
    raise PolicyViolation(f"cwd denied by policy {policy.profile!r}: {cwd!r}")


def merge_env(env: Mapping[str, str] | None) -> dict[str, str]:
    merged = dict(os.environ)
    if env:
        for k, v in env.items():
            if k in BLOCKED_ENV:
                raise PolicyViolation(f"blocked env passthrough: {k}")
            merged[k] = v
    for k in BLOCKED_ENV:
        merged.pop(k, None)
    return merged


@dataclass
class Job:
    id: str
    session_id: str
    argv: list[str]
    status: str = "running"  # running | done | terminated | timed-out
    output: bytearray = field(default_factory=bytearray, repr=False)
    truncated_bytes: int = 0
    exit_code: int | None = None
    timed_out: bool = False
    started: float = field(default_factory=time.time)
    _proc: subprocess.Popen | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self, cap: int) -> dict[str, Any]:
        with self._lock:
            data = bytes(self.output[:cap])
        return {
            "job_id": self.id,
            "status": self.status,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "output": data.decode("utf-8", errors="replace"),
            "truncated_bytes": self.truncated_bytes,
        }


class NoSuchJob(KeyError):
    pass


class JobManager:
    """Owns child processes; the broker is their parent, nobody else."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    def start(
        self,
        session_id: str,
        argv: list[str],
        policy: GrantedPolicy,
        *,
        cwd: str = ".",
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> Job:
        argv = list(argv)
        if not argv:
            raise ValueError("empty argv")
        check_process(policy, argv)
        check_cwd(policy, cwd)
        limit = policy.max_output_bytes or 1_000_000
        wall = timeout or policy.max_wall_seconds

        popen_kwargs: dict[str, Any] = {
            "cwd": str(cwd),
            "env": merge_env(env),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(argv, **popen_kwargs)
        except FileNotFoundError:
            job = Job(id=f"job_{uuid.uuid4().hex[:12]}", session_id=session_id, argv=argv)
            job.status = "done"
            job.exit_code = 127
            with job._lock:
                job.output += f"executable not found: {argv[0]}".encode()
            with self._lock:
                self._jobs[job.id] = job
            return job

        job = Job(id=f"job_{uuid.uuid4().hex[:12]}", session_id=session_id, argv=argv)
        job._proc = proc
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._drain, args=(job, limit), daemon=True).start()
        threading.Thread(target=self._watch, args=(job, wall), daemon=True).start()
        return job

    def _drain(self, job: Job, limit: int) -> None:
        proc = job._proc
        assert proc is not None and proc.stdout is not None
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                with job._lock:
                    room = limit - len(job.output)
                    if room > 0:
                        job.output += chunk[:room]
                    job.truncated_bytes += max(0, len(chunk) - max(0, room))
        except (ValueError, OSError):
            pass  # stdio torn down during terminate()

    def _watch(self, job: Job, wall: float) -> None:
        proc = job._proc
        assert proc is not None
        try:
            proc.wait(timeout=wall)
        except subprocess.TimeoutExpired:
            with job._lock:
                job.timed_out = True
            self._kill(job)
            proc.wait()
        with job._lock:
            job.exit_code = proc.returncode
            if job.status == "running":
                job.status = "timed-out" if job.timed_out else "done"

    def _kill(self, job: Job) -> None:
        proc = job._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            if os.name != "nt":
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    proc.terminate()
            else:
                proc.terminate()
        except (ProcessLookupError, PermissionError, OSError):
            return
        try:
            proc.wait(timeout=_TERMINATE_GRACE)
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        proc.kill()
                else:
                    proc.kill()
            except (ProcessLookupError, PermissionError, OSError):
                pass

    def get(self, job_id: str) -> Job:
        with self._lock:
            try:
                return self._jobs[job_id]
            except KeyError:
                raise NoSuchJob(job_id) from None

    def terminate(self, job_id: str) -> Job:
        job = self.get(job_id)
        with job._lock:
            if job.status != "running":
                return job
            job.status = "terminated"
        self._kill(job)
        return job

    def reap_session(self, session_id: str) -> int:
        with self._lock:
            ids = [j.id for j in self._jobs.values() if j.session_id == session_id]
        for jid in ids:
            try:
                self.terminate(jid)
            except (NoSuchJob, OSError):
                pass
        return len(ids)

    def drop(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
