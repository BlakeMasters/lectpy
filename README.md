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

## What you can create

Build traced technical explanations or plain Python documents with text, code,
bounded tables, local media, pen-aware whiteboards, and user-controlled reference
browser windows. Both viewers offer Reader, Presenter and Inspector styles. Local
assets travel with static exports.

```python
from lecture import browser_close, browser_open, image, whiteboard

def main():
    image("assets/diagram.svg", alt="Describe the diagram here")
    whiteboard("Working notes")
    browser_open("https://arxiv.org/", window_id="paper", width=1100, height=760)
    browser_close("paper")
```

Whiteboards provide pen/highlighter, eraser, shapes, text, undo/redo and
SVG/PNG/editable-JSON export. Drawings survive stepping but must be saved before
reloading. Pair styluses through the OS; pressure depends on browser/device support.
Reference windows render an accessible open/focus control, preserve a named window,
accept bounded size/position options, and can be closed by a later recorded event.
Popup-blocked browsers retain a normal fallback link.

Reusable `PresentationStyle` and `WhiteboardOptions` objects keep configuration
local to the content. Start with `TECHNICAL`, `PAPER`, or `SEMINAR`, then override
fonts, output highlighting, spacing, and sizing per section. See
[presentation options](docs/OPTIONS.md) and the six-scene
[runnable example](examples/presentation_options.py).

## Design (summary)

Python SDK → v1 event log + artifacts → static viewer or React shell.
An optional live workflow connects the React shell to the local capability broker.

- **Viewers:** dependency-free static HTML and a React/TypeScript shell. Live
  terminal tools and the whiteboard engine load separately from replay startup.
- **Core pattern:** microkernel + registries, not a monolithic notebook app.
- **Local privileged layer:** capability broker (`src/lecture/broker/`) owns
  kernels, processes, PTYs, artifacts, permissions. Browser never spawns natively.
- **Python execution:** `TraceRuntime` (edtrace-compatible `sys.settrace` stepper)
  is one provider; Jupyter kernels are the general REPL provider (v0.3).
- **State:** ordered execution events; whiteboard annotations are separate local
  viewer state. Collaboration and general live component actions remain future work.
- **Data:** small JSON events and content-addressed files; large local media is
  captured and exported in chunks. Tables and inspectors provide bounded previews.
- **Policy:** local capability profiles and a broker token. Profiles do not turn
  ordinary Python execution into an OS sandbox; see the security documentation.
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
  providers/          execution providers, including trace/process/Jupyter adapters
  broker/             in-process capability broker (session/event/artifact services)
  plugins.py          renderer / execution / inspector registries
  export_static.py    static bundle writer (lecture.json + artifacts + index.html)
  cli.py              lecture init|trace|build|serve|doctor|test
schemas/              JSON schemas (event v1, manifest v1)
frontend/             React shell, lazy tools, and frontend tests
examples/             executable .py lectures
tests/                protocol / replay-golden / security / perf-smoke suites
docs/                 architecture / roadmap / security / authoring
```

## Status

The package is pre-1.0 and keeps the v1 event envelope compatible. Implemented
authoring workflows are documented in [Authoring](docs/AUTHORING.md); architecture
and roadmap documents also describe planned capabilities. Plot specifications and
arbitrary custom components still use recorded placeholders unless a renderer is
provided; whiteboards and reference browser windows are working stock components.

## Compatibility

`lecture.compat.edtrace`-style API (`text`, `image`, `video`, `link`, `plot`,
`note`, `inspect`, `system_text`, comment directives `# @inspect`, `# @hide`,
`# @step-over`, `# @clear`) is preserved at behavior level; backends are all
redesigned (explicit `ExecutionContext`, ordered event log, CAS blobs, lazy
object handles, sanitized HTML, brokered processes).

## License

MIT — see `LICENSE`.
