"""Broker-owned interactive PTYs. The browser receives byte frames only.

Backends: `winpty` on Windows (real ConPTY), `posix-pty` via openpty
elsewhere. There is deliberately no pipe fallback: a pipe is not a terminal
(no job control, no resize, buffering lies), and silently downgrading would
break the terminal contract the shell relies on.

Wire format is bytes end-to-end (base64 inside WS JSON frames) so partial
UTF-8 sequences survive chunk boundaries; the shell decodes incrementally.
Detach does NOT kill (reattach replays the retained ring); explicit kill,
DELETE, or session close reaps. All sizes/bandwidths are capped.
"""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..policy import GrantedPolicy, PolicyViolation
from .jobs import check_cwd, merge_env

RING_CAP = 256 * 1024
READ_CHUNK = 65536


class NoPtyBackend(RuntimeError):
    pass


def detect_backend() -> str:
    if os.name == "nt":
        try:
            import winpty  # noqa: F401

            return "winpty"
        except ImportError:
            return "none"
    try:
        import pty  # noqa: F401

        return "posix-pty"
    except ImportError:
        return "none"


def default_shell() -> list[str]:
    if os.name == "nt":
        return [os.environ.get("COMSPEC", "cmd.exe")]
    return [os.environ.get("SHELL", "/bin/sh")]


class _WinptyProc:
    def __init__(
        self, argv: list[str], cwd: str, env: Mapping[str, str], cols: int, rows: int
    ) -> None:
        from winpty import PtyProcess

        self._proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols))

    def read(self, n: int) -> bytes:
        data = self._proc.read(n)
        if isinstance(data, str):
            return data.encode("utf-8", errors="replace")
        return bytes(data)

    def write(self, data: bytes) -> None:
        # pywinpty takes str (Cython rejects bytes); decode at the boundary.
        try:
            self._proc.write(data.decode("utf-8", errors="replace"))
        except (OSError, EOFError):
            pass

    def set_size(self, cols: int, rows: int) -> None:
        self._proc.setwinsize(rows, cols)

    def isalive(self) -> bool:
        try:
            return bool(self._proc.isalive())
        except (OSError, EOFError):
            return False

    def kill(self) -> None:
        # pexpect-style API: terminate() first, then kill(sig). Either may
        # raise once the process is already gone — best effort throughout.
        try:
            self._proc.terminate()
        except Exception:
            pass
        try:
            if self.isalive():
                import signal

                self._proc.kill(signal.SIGTERM)
        except Exception:
            pass

    def exit_code(self) -> int | None:
        for attr in ("exitstatus", "status", "returncode"):
            v = getattr(self._proc, attr, None)
            if isinstance(v, int):
                return v
        return None


class _PosixPtyProc:
    def __init__(
        self, argv: list[str], cwd: str, env: Mapping[str, str], cols: int, rows: int
    ) -> None:
        import pty

        self._master, slave = pty.openpty()
        self.set_size(cols, rows)
        self._proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=dict(env),
            stdin=slave,
            stdout=slave,
            stderr=slave,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(slave)
        self._closed = False

    def read(self, n: int) -> bytes:
        import select

        r, _, _ = select.select([self._master], [], [], 0.2)
        if not r:
            return b""
        try:
            return os.read(self._master, n)
        except OSError:
            return b""

    def write(self, data: bytes) -> None:
        try:
            os.write(self._master, data)
        except OSError:
            pass

    def set_size(self, cols: int, rows: int) -> None:
        import fcntl
        import struct
        import termios

        try:
            fcntl.ioctl(self._master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        except OSError:
            pass

    def isalive(self) -> bool:
        return self._proc.poll() is None

    def kill(self) -> None:
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                self._proc.kill()
            except (ProcessLookupError, PermissionError, OSError):
                pass

    def exit_code(self) -> int | None:
        return self._proc.poll()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                os.close(self._master)
            except OSError:
                pass


@dataclass
class PtySession:
    id: str
    session_id: str
    argv: list[str]
    cols: int
    rows: int
    backend: str
    alive: bool = True
    exit_code: int | None = None
    started: float = field(default_factory=time.time)
    _proc: Any = field(default=None, repr=False)
    _buf: bytearray = field(default_factory=bytearray, repr=False)
    _attached: set = field(default_factory=set, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class NoSuchPty(KeyError):
    pass


class PtyManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ptys: dict[str, PtySession] = {}

    @property
    def backend(self) -> str:
        return detect_backend()

    def spawn(
        self,
        session_id: str,
        policy: GrantedPolicy,
        *,
        argv: list[str] | None = None,
        cols: int = 100,
        rows: int = 30,
        cwd: str = ".",
        env: Mapping[str, str] | None = None,
    ) -> PtySession:
        # Interactive shells are ambient authority: only the explicit
        # local-trusted profile may open one. "sandbox" profiles need a real
        # sandbox provider (v0.7), which does not exist yet in v0.3.
        if policy.process != "allow":
            raise PolicyViolation(
                f"interactive PTY denied by policy {policy.profile!r} "
                f"(mode={policy.process}). v0.3 spawns shells for local-trusted only."
            )
        backend = detect_backend()
        if backend == "none":
            raise NoPtyBackend("no PTY backend on this host (need pywinpty on Windows)")
        cols = max(20, min(500, int(cols)))
        rows = max(5, min(200, int(rows)))
        cmd = list(argv) if argv else default_shell()
        if not cmd:
            raise ValueError("empty argv")
        check_cwd(policy, cwd)
        merged = merge_env(env)
        if backend == "winpty":
            proc: Any = _WinptyProc(cmd, str(cwd), merged, cols, rows)
        else:
            proc = _PosixPtyProc(cmd, str(cwd), merged, cols, rows)
        sess = PtySession(
            id=f"pty_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            argv=cmd,
            cols=cols,
            rows=rows,
            backend=backend,
            _proc=proc,
        )
        with self._lock:
            self._ptys[sess.id] = sess
        threading.Thread(target=self._pump, args=(sess,), daemon=True).start()
        return sess

    def _pump(self, sess: PtySession) -> None:
        idle_empty = 0
        while True:
            try:
                chunk = sess._proc.read(READ_CHUNK)
            except (EOFError, OSError):
                chunk = b""
            if chunk:
                idle_empty = 0
                with sess._lock:
                    sess._buf += chunk
                    if len(sess._buf) > RING_CAP:
                        del sess._buf[: len(sess._buf) - RING_CAP]
                    attached = list(sess._attached)
                for q in attached:
                    try:
                        q.put_nowait(bytes(chunk))
                    except queue.Full:
                        pass
            else:
                if not sess._proc.isalive():
                    break
                idle_empty += 1
            # posix read() returns b"" on timeout ticks; winpty blocks instead.
            if sess.backend != "winpty" and idle_empty > 6000:
                break  # ~20 min idle with a live child: stop pumping, keep PTY
        with sess._lock:
            sess.alive = False
            try:
                sess.exit_code = sess._proc.exit_code()
            except (OSError, EOFError):
                sess.exit_code = None
            attached = list(sess._attached)
        for q in attached:
            try:
                q.put_nowait(None)  # sentinel: EOF
            except queue.Full:
                pass
        if sess.backend != "winpty" and hasattr(sess._proc, "close"):
            try:
                sess._proc.close()
            except OSError:
                pass

    def get(self, pty_id: str) -> PtySession:
        with self._lock:
            try:
                return self._ptys[pty_id]
            except KeyError:
                raise NoSuchPty(pty_id) from None

    def write(self, pty_id: str, data: bytes) -> None:
        sess = self.get(pty_id)
        if not sess.alive:
            raise NoSuchPty(f"{pty_id} exited")
        sess._proc.write(data[:65536])

    def resize(self, pty_id: str, cols: int, rows: int) -> None:
        sess = self.get(pty_id)
        sess.cols = max(20, min(500, int(cols)))
        sess.rows = max(5, min(200, int(rows)))
        try:
            sess._proc.set_size(sess.cols, sess.rows)
        except (OSError, EOFError):
            pass

    def history(self, pty_id: str) -> bytes:
        sess = self.get(pty_id)
        with sess._lock:
            return bytes(sess._buf)

    def attach(self, pty_id: str) -> queue.Queue[bytes | None]:
        sess = self.get(pty_id)
        q: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        with sess._lock:
            sess._attached.add(q)
        return q

    def detach(self, pty_id: str, q: queue.Queue[bytes | None]) -> None:
        try:
            sess = self.get(pty_id)
        except NoSuchPty:
            return
        with sess._lock:
            sess._attached.discard(q)

    def kill(self, pty_id: str) -> PtySession:
        sess = self.get(pty_id)
        try:
            sess._proc.kill()
        except Exception:
            pass  # best effort: the pump observes exit independently
        with sess._lock:
            sess.alive = False
        return sess

    def remove(self, pty_id: str) -> None:
        with self._lock:
            sess = self._ptys.pop(pty_id, None)
        if sess is not None:
            try:
                sess._proc.kill()
            except (OSError, EOFError):
                pass

    def reap_session(self, session_id: str) -> int:
        with self._lock:
            ids = [p.id for p in self._ptys.values() if p.session_id == session_id]
        for pid in ids:
            try:
                self.kill(pid)
            except (NoSuchPty, OSError):
                pass
            self.remove(pid)
        return len(ids)
