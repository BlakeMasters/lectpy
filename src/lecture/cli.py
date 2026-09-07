"""`lecture` CLI — init | trace | build | serve | doctor | test."""

from __future__ import annotations

import argparse
import http.server
import json
import sys
from functools import partial
from pathlib import Path


def cmd_init(args: argparse.Namespace) -> int:
    dest = Path(args.dir or ".")
    dest.mkdir(parents=True, exist_ok=True)
    lec = dest / "lecture_01.py"
    if not lec.exists():
        lec.write_text(
            '"""My first lectpy lecture — plain executable Python."""\n'
            "from lecture import text, inspect_value, plot\n\n\n"
            "def main():\n"
            '    text("# Hello, lectpy\\nStep through this narrative.")\n'
            "    w = 1.0\n"
            '    inspect_value("w", w)\n'
            "    for _ in range(5):\n"
            "        w -= 0.1 * (2 * w)\n"
            '        inspect_value("w", w)\n'
            '    plot({"data": {"values": [{"x": 1, "y": 2}]}, "mark": "line",\n'
            '          "encoding": {"x": {"field": "x"}, "y": {"field": "y"}}})\n',
            encoding="utf-8",
        )
    toml = dest / "lecture.toml"
    if not toml.exists():
        toml.write_text(
            "[lecture]\nformat-version = 1\n\n"
            '[runtimes.python]\nprovider = "trace"\n\n'
            '[policy.default]\nnetwork = "deny"\nprocess = "sandbox"\n\n'
            '[export.static]\ninteractive-fallback = "recorded"\n',
            encoding="utf-8",
        )
    print(f"initialized lecture in {dest.resolve()}")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactStore
    from .ir import LectureManifest, sha256_file
    from .policy import default_policy
    from .trace import TraceExecutor

    src = Path(args.source)
    if not src.exists():
        print(f"error: no such file: {src}", file=sys.stderr)
        return 2
    profile = args.policy or "local-trusted"
    policy = default_policy(profile)
    store = ArtifactStore(args.artifact_dir or ".lecture/artifacts")
    ex = TraceExecutor(policy=policy, artifacts=store)
    ctx = ex.trace_file(src)
    out = Path(args.out) if args.out else Path("var/traces") / (src.stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = LectureManifest(
        title=src.stem,
        source_file=str(src),
        source_sha256=sha256_file(src),
        runtime="trace",
        policy_profile=profile,
    )
    payload = {"manifest": manifest.to_dict(), "events": ctx.log.to_list()}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    n_steps = sum(1 for e in ctx.log.to_list() if e["kind"] == "step")
    print(f"traced {src} -> {out} ({len(ctx.log)} events, {n_steps} steps)")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactStore
    from .export_static import export_static
    from .ir import Checkpoint, LectureManifest, sha256_file
    from .policy import default_policy
    from .trace import TraceExecutor

    src = Path(args.source)
    if not src.exists():
        print(f"error: no such file: {src}", file=sys.stderr)
        return 2
    policy = default_policy(args.policy or "local-trusted")
    store = ArtifactStore(args.artifact_dir or ".lecture/artifacts")
    ctx = TraceExecutor(policy=policy, artifacts=store).trace_file(src)
    manifest = LectureManifest(
        title=args.title or src.stem,
        source_file=str(src),
        source_sha256=sha256_file(src),
        runtime="trace",
        policy_profile="static",
    )
    cp = Checkpoint(
        flavor="recorded",
        source_sha256=manifest.source_sha256,
        event_seq=len(ctx.log),
        runtime_id="trace",
        policy_profile="static",
        artifact_hashes=store.list_refs(),
        replayable=True,
        side_effects=[],
    )
    out = export_static(ctx, manifest, args.out or f"dist/{src.stem}", checkpoint=cp)
    print(f"built static bundle -> {out.resolve()} ({len(ctx.log)} events)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    root = Path(args.dir or "dist/lecture_01")
    if not root.exists():
        print(f"error: no such dir: {root}", file=sys.stderr)
        return 2
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port or 8000), handler)
    print(f"serving {root.resolve()} at http://127.0.0.1:{httpd.server_port}/ (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    import platform

    ok = True
    print(f"python {sys.version.split()[0]} on {platform.system()} {platform.release()}")
    for mod, hint in (
        ("jupyter_client", "pip install lectpy[jupyter] for kernel provider (v0.3+)"),
        ("numpy", "pip install lectpy[viz] for array previews"),
    ):
        try:
            __import__(mod)
            print(f"  [ok] optional dep '{mod}' present")
        except ImportError:
            print(f"  [..] optional dep '{mod}' missing — {hint}")
    for d in (".lecture/artifacts", "var/traces", "dist"):
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
            print(f"  [ok] writable: {d}")
        except OSError as e:
            print(f"  [FAIL] not writable: {d}: {e}")
            ok = False
    try:
        from .events import EventLog
        from .policy import default_policy

        log = EventLog("sess_doctor", "exec_doctor")
        log.append("text", {"markdown": "ok"})
        assert log.check_monotonic()
        default_policy("static")
        print("  [ok] event protocol + policy profiles")
    except Exception as e:
        print(f"  [FAIL] core self-test: {e}")
        ok = False
    print("doctor: " + ("GREEN" if ok else "ISSUES FOUND"))
    return 0 if ok else 1


def cmd_test(_args: argparse.Namespace) -> int:
    import subprocess

    r = subprocess.run([sys.executable, "-m", "pytest", "-q"])
    return r.returncode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lecture", description="lectpy lecture toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="scaffold a lecture project")
    s.add_argument("dir", nargs="?", default=".")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("trace", help="trace a .py lecture to a JSON event log")
    s.add_argument("source")
    s.add_argument("--out", default=None)
    s.add_argument("--policy", default="local-trusted")
    s.add_argument("--artifact-dir", default=None)
    s.set_defaults(func=cmd_trace)

    s = sub.add_parser("build", help="build a static replay bundle")
    s.add_argument("source")
    s.add_argument("--out", default=None)
    s.add_argument("--title", default=None)
    s.add_argument("--policy", default="local-trusted")
    s.add_argument("--artifact-dir", default=None)
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("serve", help="serve a static bundle on loopback")
    s.add_argument("dir", nargs="?", default="dist/lecture_01")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("doctor", help="environment + self-test diagnostics")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("test", help="run the test suite")
    s.set_defaults(func=cmd_test)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
