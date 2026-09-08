# lectpy — Superior Interactive Python Lecture Platform

Plain-Python executable lectures with debugger-like stepping, visible program
state, concise author rendering primitives, and static publishing — rebuilt on
a small stable **lecture microkernel** with replaceable providers.

This repo is the successor-core to `edtrace`-style workflows:

```python
from lecture import text, inspect_value

def main():
    text("# Gradient descent")
    w = 1.0
    inspect_value("w", w)
    for step in range(5):
        w -= 0.1 * (2 * w)
        inspect_value("w", w)
```

```bash
pip install -e ".[dev]"
lecture trace examples/lecture_01.py --out var/traces/lecture_01.json
lecture build examples/lecture_01.py --out dist/lecture_01
lecture serve dist/lecture_01
```

`lecture.toml` can provide the entrypoint, title, and execution settings. Run
`lecture check` to validate a project without executing it, or `lecture build`
to build the configured entrypoint. For a document with no line stepping, use
`lecture build examples/document.py --provider python`. See
[Authoring](docs/AUTHORING.md) for configuration precedence and supported settings.

## Design (summary)

```
Python authoring SDK → versioned lecture/event protocol → browser app → capability broker → runtimes
```

- **Canonical UI:** browser TypeScript app (+ optional Tauri wrapper). v0.1 ships a
  dependency-free static replay viewer; the full React shell lands in v0.2.
- **Core pattern:** microkernel + registries, not a monolithic notebook app.
- **Local privileged layer:** capability broker (`src/lecture/broker/`) owns
  kernels, processes, PTYs, artifacts, permissions. Browser never spawns natively.
- **Python execution:** `TraceRuntime` (edtrace-compatible `sys.settrace` stepper)
  is one provider; Jupyter kernels are the general REPL provider (v0.3).
- **State:** ordered, single-writer **event log** for execution; CRDT (Yjs/Automerge)
  only for collaboratively edited *source* (v0.5). Never CRDT for runtime effects.
- **Data:** JSON control plane + content-addressed blobs + Arrow IPC for arrays (lazy).
- **Security:** capability policy (`static`, `local-trusted`, `local-restricted`,
  `classroom`, `public-untrusted`) layered over OS/container/WASM isolation.
- **Publishing:** static replay bundle is first-class, with capability-degradation rules.

See `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `docs/SECURITY.md`,
`docs/AUTHORING.md`.

## Repo layout

```
src/lecture/          Python SDK + microkernel core
  __init__.py         author-facing primitives (text, plot, inspect, …)
  context.py          scoped ExecutionContext (no process-global accumulator)
  events.py           versioned event envelope + validation
  ir.py               lecture IR / manifest / checkpoint descriptor
  artifacts.py        content-addressed blob store
  policy.py           capability profiles + enforcement helpers
  sanitize.py         markdown → sanitized HTML (no raw dangerouslySetInnerHTML path)
  trace.py            TraceExecutor (sys.settrace pedagogical stepper)
  providers/          trace / process-one-shot runtimes (jupyter, pty in roadmap)
  broker/             in-process capability broker (session/event/artifact services)
  plugins.py          renderer / execution / inspector registries
  export_static.py    static bundle writer (lecture.json + artifacts + index.html)
  cli.py              lecture init|trace|build|serve|doctor|test
schemas/              JSON schemas (event v1, manifest v1)
frontend/             TS shell stub (full app in v0.2; replay viewer is static HTML)
examples/             executable .py lectures
tests/                protocol / replay-golden / security / perf-smoke suites
docs/                 architecture / roadmap / security / authoring
```

## Status

**v0.1.0 — Protocol & compatibility core (this milestone).** Lecture IR, event
schemas, scoped author SDK, tracer, CAS store, static export + replay, CLI,
test suites. See `docs/ROADMAP.md` for v0.2–v0.7.

## Compatibility

`lecture.compat.edtrace`-style API (`text`, `image`, `video`, `link`, `plot`,
`note`, `inspect`, `system_text`, comment directives `# @inspect`, `# @hide`,
`# @step-over`, `# @clear`) is preserved at behavior level; backends are all
redesigned (explicit `ExecutionContext`, ordered event log, CAS blobs, lazy
object handles, sanitized HTML, brokered processes).

## License

MIT — see `LICENSE`.
