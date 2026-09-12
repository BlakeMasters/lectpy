"""`lecture` CLI — init | trace | build | serve | doctor | test."""

from __future__ import annotations

import argparse
import http.server
import json
import sys
from functools import partial
from pathlib import Path

from .config import ConfigError, ProjectConfig, load_project
from .policy import GrantedPolicy


def _execution_settings(
    args: argparse.Namespace,
) -> tuple[ProjectConfig, Path, GrantedPolicy, str]:
    config = load_project(args.source, args.config)
    if args.source:
        src = Path(args.source).resolve()
    elif config.entry:
        src = (config.root / config.entry).resolve()
    else:
        raise ConfigError("provide a source file or set lecture.entry in lecture.toml")
    if not src.is_file():
        raise ConfigError(f"no such source file: {src}")
    provider = args.provider or config.provider
    return config, src, config.execution_policy(args.policy), provider


def cmd_check(args: argparse.Namespace) -> int:
    config, src, policy, provider = _execution_settings(args)
    try:
        compile(src.read_text(encoding="utf-8"), str(src), "exec")
    except SyntaxError as exc:
        raise ConfigError(f"{src}:{exc.lineno}: {exc.msg}") from exc
    print(f"checked {src} (provider={provider}, policy={policy.profile})")
    if config.path:
        print(f"config: {config.path}")
    return 0


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
            '[lecture]\nformat-version = 1\nentry = "lecture_01.py"\ntitle = "My lecture"\n\n'
            '[runtimes.python]\nprovider = "trace"\n\n'
            '[policy.default]\nprofile = "local-trusted"\n\n'
            '[export.static]\ninteractive-fallback = "recorded"\n',
            encoding="utf-8",
        )
    print(f"initialized lecture in {dest.resolve()}")
    return 0


def cmd_trace(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactStore
    from .ir import LectureManifest, sha256_file
    from .trace import TraceExecutor

    config, src, policy, provider = _execution_settings(args)
    store = ArtifactStore(args.artifact_dir or config.root / ".lecture/artifacts")
    ex = TraceExecutor(policy=policy, artifacts=store, record_steps=provider == "trace")
    ctx = ex.trace_file(src)
    out = Path(args.out) if args.out else config.root / "var/traces" / (src.stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest = LectureManifest(
        title=args.title or config.title or src.stem,
        source_file=str(src),
        source_sha256=sha256_file(src),
        runtime=provider,
        policy_profile=policy.profile,
        view=args.view or config.view,
    )
    payload = {"manifest": manifest.to_dict(), "events": ctx.log.to_list()}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    n_steps = sum(1 for e in ctx.log.to_list() if e["kind"] == "step")
    print(f"traced {src} -> {out} ({len(ctx.log)} events, {n_steps} steps)")
    return 1 if any(e.kind == "error" for e in ctx.log.subscribe()) else 0


def cmd_build(args: argparse.Namespace) -> int:
    from .artifacts import ArtifactStore
    from .export_static import export_static
    from .ir import Checkpoint, LectureManifest, sha256_file
    from .trace import TraceExecutor

    config, src, policy, provider = _execution_settings(args)
    store = ArtifactStore(args.artifact_dir or config.root / ".lecture/artifacts")
    ctx = TraceExecutor(
        policy=policy, artifacts=store, record_steps=provider == "trace"
    ).trace_file(src)
    manifest = LectureManifest(
        title=args.title or config.title or src.stem,
        source_file=str(src),
        source_sha256=sha256_file(src),
        runtime=provider,
        policy_profile="static",
        view=args.view or config.view,
    )
    cp = Checkpoint(
        flavor="recorded",
        source_sha256=manifest.source_sha256,
        event_seq=len(ctx.log),
        runtime_id=provider,
        policy_profile="static",
        artifact_hashes=store.list_refs(),
        replayable=True,
        side_effects=[],
    )
    out = export_static(ctx, manifest, args.out or config.root / "dist" / src.stem, checkpoint=cp)
    print(f"built static bundle -> {out.resolve()} ({len(ctx.log)} events)")
    return 1 if any(e.kind == "error" for e in ctx.log.subscribe()) else 0


def cmd_serve(args: argparse.Namespace) -> int:
    root = Path(args.dir or "dist/lecture_01")
    if not root.exists():
        print(f"error: no such dir: {root}", file=sys.stderr)
        return 2
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port or 8000), handler)
    automation = None
    if args.scripts:
        from .broker.automation import AutomationService
        from .broker.automation_http import automation_handler

        try:
            automation = AutomationService(
                Path(args.scripts).resolve(),
                json.loads((root / "lecture.json").read_text(encoding="utf-8")),
                f"http://127.0.0.1:{httpd.server_port}",
                headless=args.headless,
            )
            httpd.RequestHandlerClass = automation_handler(root.resolve(), automation)
        except (ValueError, OSError) as exc:
            httpd.server_close()
            raise ConfigError(str(exc)) from exc
        print("Local scripts enabled. Open a control to launch the managed browser.")
    print(f"serving {root.resolve()} at http://127.0.0.1:{httpd.server_port}/ (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        if automation:
            automation.close()
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


def cmd_broker(args: argparse.Namespace) -> int:
    from .broker.auth import load_or_create_token
    from .broker.server import BrokerServer, ServerConfig

    token_path = args.token_path or ".lecture/broker.token"
    token = load_or_create_token(args.token, token_path)
    config = ServerConfig(
        host=args.host or "127.0.0.1",
        port=args.port or 7888,
        token=token,
        token_path=token_path,
        artifact_root=args.artifact_dir or ".lecture/artifacts",
        cwd=args.cwd or ".",
    )
    server = BrokerServer(config).start()
    if config.host not in ("127.0.0.1", "localhost", "::1"):
        print("WARNING: binding a non-loopback address; put TLS + auth in front.")
    print(f"lectured {server.url} (ws on :{server.ws_port})")
    print(f"token: {token_path} (or $LECTPY_TOKEN)")
    print(f"token value (loopback dev convenience): {token}")
    print("Ctrl+C to stop; sessions/jobs/ptys/kernels die with the daemon.")
    try:
        while True:
            import time as _time

            _time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lecture", description="lectpy lecture toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="scaffold a lecture project")
    s.add_argument("dir", nargs="?", default=".")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("trace", help="trace a .py lecture to a JSON event log")
    s.add_argument("source", nargs="?")
    s.add_argument("--out", default=None)
    s.add_argument("--title", default=None)
    s.add_argument("--view", choices=("reader", "presenter", "inspector"), default=None)
    s.add_argument("--config", default=None)
    s.add_argument("--provider", choices=("trace", "python"), default=None)
    s.add_argument("--policy", default=None)
    s.add_argument("--artifact-dir", default=None)
    s.set_defaults(func=cmd_trace)

    s = sub.add_parser("build", help="build a static replay bundle")
    s.add_argument("source", nargs="?")
    s.add_argument("--out", default=None)
    s.add_argument("--title", default=None)
    s.add_argument("--view", choices=("reader", "presenter", "inspector"), default=None)
    s.add_argument("--config", default=None)
    s.add_argument("--provider", choices=("trace", "python"), default=None)
    s.add_argument("--policy", default=None)
    s.add_argument("--artifact-dir", default=None)
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("check", help="check project config and Python syntax without executing")
    s.add_argument("source", nargs="?")
    s.add_argument("--config", default=None)
    s.add_argument("--provider", choices=("trace", "python"), default=None)
    s.add_argument("--policy", default=None)
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("serve", help="serve a static bundle on loopback")
    s.add_argument("dir", nargs="?", default="dist/lecture_01")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument(
        "--scripts", help="enable registered Playwright scripts from this lecture source"
    )
    s.add_argument(
        "--headless", action="store_true", help="run managed browsers headlessly (testing)"
    )
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("doctor", help="environment + self-test diagnostics")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("test", help="run the test suite")
    s.set_defaults(func=cmd_test)

    s = sub.add_parser("broker", help="run the loopback capability broker daemon")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=7888)
    s.add_argument("--token", default=None)
    s.add_argument("--token-path", default=None)
    s.add_argument("--artifact-dir", default=None)
    s.add_argument("--cwd", default=None)
    s.set_defaults(func=cmd_broker)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (ConfigError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
