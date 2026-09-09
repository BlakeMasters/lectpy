# Authoring — plain Python lectures

Level A (no frontend code):

```python
from lecture import text, note, inspect_value, plot

def main():
    text("# Gradient descent\nStepping shows live state.")
    w = 1.0
    inspect_value("w", w)
    for i in range(5):
        w -= 0.1 * (2 * w)
        inspect_value("w", w)
    plot({"data": {"values": [{"x": 1, "y": 2}]}, "mark": "line",
          "encoding": {"x": {"field": "x"}, "y": {"field": "y"}}})
```

Primitives: `text`, `code`, `table`, `note`, `image`, `video`, `link`, `plot`, `equation`, `uml`, `inspect_value`,
`clear`, `system_text`, `component`, `whiteboard`, `browser_open`, `browser_close`, `terminal`.
All emit typed events on the
scoped `ExecutionContext` — never a process-global accumulator.

Directives (edtrace-compatible, plus structured API):

```python
from lecture import inspect, hide, step_over

@inspect("w")          # always show w at each traced line in scope
@hide                  # hide helper from pedagogical stepping
def helper(): ...

def main():
    x = 1  # @inspect x
    y = 2  # @hide
    # @clear
    # @step-over
```

Project settings live in `lecture.toml`:

```toml
[lecture]
format-version = 1
entry = "lecture_01.py"
title = "Gradient descent"

[runtimes.python]
provider = "trace"   # or "python" to render main() without line stepping

[policy.default]
profile = "local-trusted"

[export.static]
interactive-fallback = "recorded"
```

Run `lecture check` to validate configuration and source syntax without running
the lecture. Run `lecture build` to execute the configured entry and produce an
offline replay in `dist/<entry-name>/`. `lecture trace` writes a JSON history to
`var/traces/<entry-name>.json`. Both use the same configured provider.

The `trace` provider records Python line steps and visible locals. The `python`
provider calls the same synchronous `main()` and records only emitted outputs;
use it for articles, reports, and pages where the code is an implementation
detail. Both use the caller's Python environment and working directory. Relative
file I/O inside the author script is ordinary Python; anchor data paths with
`Path(__file__).parent` when the project may be launched from another directory.
The Python provider does not install a tracer or impose a wall-clock interrupt
on `main()`; trace wall-time checks occur at traced lines.

Configuration is discovered by walking upward from the explicit source file, or
from the current directory when no source is supplied. `--config path/to/lecture.toml`
selects a particular file. Configured entry and filesystem paths resolve relative
to that file. Default output/artifact directories are rooted there too. Explicit
CLI paths resolve relative to the current directory.

Use `--title`, `--provider trace|python`, a positional source, or `--out` to
override a project default. `--policy local-trusted` selects that entire execution
profile, overriding configured policy fields. The execution profile governs the
authoring run; `lecture build` always produces a static delivery manifest.
`--policy static` reports a configuration error before executing anything.

`[policy.default]` also accepts `network`, `process`, `filesystem-read`,
`filesystem-write`, `allow-network-hosts`, `max-output-bytes`, `max-events`, and
`max-wall-seconds`. Paths and host lists are string arrays. Limits are positive
integers, except wall time which may be fractional. These settings govern SDK and
provider operations; they do not sandbox arbitrary local Python code.

Unknown or not-yet-implemented settings produce a useful error instead of being
silently ignored. Jupyter remains available through the broker API; it is not yet
a CLI document provider. This replaces older scaffolds that included placeholder
`kernel` and TypeScript runtime settings.

CLI exit codes: `0` means success, `1` means execution recorded an error (the
partial replay is retained for inspection), and `2` means a configuration, syntax
check, or filesystem error. Renderers also display errors that occurred before
the first trace step.

Text, media, and inspection outputs can be published without any trace history:

```bash
lecture build examples/document.py --provider python --title "A Python document"
lecture serve dist/document
```

Creation levels: **A** plain Python outputs are supported today. **B** stock
interactive components and **C** custom component plugins are being developed;
the current `component()` API records a descriptor and a static placeholder.

## Code and tabular results

```python
from lecture import code, table

def main():
    code("loss = (prediction - target) ** 2", language="python", title="Squared error")
    table(
        ({"step": i, "loss": 1 / (i + 1)} for i in range(100_000)),
        columns=["step", "loss"],
        title="Training history",
        max_rows=20,
    )
```

`code()` displays the source literally; it never executes it. `language` is a
label, with no syntax-highlighting library required. Long code lines can be
scrolled with the keyboard after focusing the block.

`table()` accepts an iterable of mappings, infers columns from the visible rows,
or uses the explicit `columns` order. It reads at most `max_rows + 1` records;
the extra record determines whether to label the preview as truncated. The
iterator is advanced by those records, so pass a fresh iterator for later work.
Missing cells and `None` display as blank. Strings are literal; other values use
short representations, and long cell text is clipped to 2,000 characters.

The default preview is 100 rows. Limits are 1,000 rows, 100 columns, and 20,000
cells per table. Use a smaller projection for wide data. This is a static preview,
not an interactive dataframe grid; unseen rows are not shipped or downloadable.
Both viewers use native HTML tables with captions, column headers, and focusable
scroll regions. Table arrow keys scroll the table without changing lecture steps.
Wide tables scroll horizontally on narrow screens.

These primitives emit compatible v1 text events with HTML plus a textual fallback.
They need no additional Python packages, browser libraries, or network requests.
Try `lecture build examples/data_story.py --provider python`.

## Reader, presenter, and inspector views

The View selector in either viewer changes the presentation of the same recording:

- Reader shows the final recorded page, without trace controls, source, or runtime
  state. It respects the last `clear()`; it is not a transcript of cleared pages.
- Presenter keeps the selected step and navigation, with larger output typography
  and no runtime state panel. Source context is optional via **Show source**; the
  current rendered output, rather than the source line, is the visual focus. It is
  a presentation style, not a slide-layout system.
- Inspector shows the selected step, runtime state, and (in the React shell) source.

Inspector's Workspace panel keeps the current frame's locals in a compact
Name/Value/Type table. New or changed values are marked at the selected step;
the call-stack cue and inspected-value summaries stay beside the output so a
rehearsal can follow data flow without turning on the source pane.

Switching to Reader does not move the stored trace cursor. Switching back to
Presenter or Inspector restores that position. The selector uses native keyboard
controls. In Reader, arrow/Home/End keys keep their normal page-scroll behavior.

Choose an author default with `--view reader|presenter|inspector` when tracing or
building, or set the project default:

```toml
[presentation]
view = "reader"
```

The `?view=` URL parameter overrides that default and can be combined with
`?step=` (`?view=presenter&step=12`). Without a default, a traced lecture opens in
Inspector and a document without steps opens in Reader. Existing v1 bundles work
with all three views. Styles change only the viewer projection, never the log.
Presenter output focus is derived from the selected step, so earlier output recedes
while newly introduced output receives the current-line accent. The accent color
and display font preset are session-local viewer choices; they do not alter a
recording.

### Section-scoped visual adjustments

Use `section()` to give related outputs a bounded presentation hint while
keeping one portable event log:

```python
from lecture import section, text, table

with section("Evidence", tone="evidence", density="compact", width="wide"):
    text("## Results")
    table(rows, title="Measured values")
```

Available tones are `neutral`, `hero`, `evidence`, `code`, and `recap`.
Density can be `compact`, `comfortable`, or `roomy`; width can be `reading`,
`wide`, or `full`; alignment can be `start` or `center`. These are projection
metadata only. The static replay and React shell use the same bounded class
vocabulary, and older readers can safely ignore the extra payload field.

## Step-driven reference windows

`browser_open(url, ...)` and `browser_close(window_id)` are recorded as ordinary
component events. In Presenter or Inspector, moving forward through a recorded
open/close event attempts to apply it from the user's step-navigation action, so
an author can make a reference page appear at the point where it is discussed and
close it later. The named `lectpy_<window_id>` handle is reused and focused on
repeat opens; moving backward reconciles owned handles without replaying
historical open commands. Reader keeps the same accessible
fallback controls without stepping.

Popup blockers may prevent the automatic attempt. Each reference output retains a
Focus/Open action, a Close action where applicable, and an ordinary fallback link,
so the lecture remains usable. Geometry is best-effort browser placement, and the
remote page is never copied into the bundle. Moving backward is a reconciliation
operation: it closes windows that are not open at the target step and never
replays an old open command merely because that command is in the visible
history. This prevents an arrow-key rewind from reopening the last reference
link as a stale popup.

## Portable media

`image(path_or_url, alt="…", title="…")` and `video(path_or_url, title="…")`
capture local files into the artifact store. Relative files resolve beside the
lecture entry file, not beside the command's current directory. For a helper
module's own assets, pass `Path(__file__).parent / "assets/diagram.svg"`.
Explicit HTTP(S), data and blob URLs stay unchanged; remote files are not downloaded.
Blob URLs are browser-session-local and are not portable exports.

`asset(path_or_bytes, mime=None)` returns a reusable `artifact:sha256:…` URI.
Bytes require a MIME type, e.g. `image(svg_bytes, mime="image/svg+xml", alt="…")`.
Use the returned URI in `image`, `video`, `link`, or component props. The exporter
copies referenced files only, records their MIME types and rewrites URLs to
bundle-relative paths. Copy the **whole output directory**, not just index.html.
Large files are captured and exported in chunks; video bytes stay out of event JSON.
The React viewer resolves assets relative to the fetched lecture.json even when
the shell lives elsewhere. Live artifact requests use the current broker token.

See [media_story.py](../examples/media_story.py). These are media elements, not a
video editor; authors remain responsible for captions/transcripts where needed.

## Whiteboards

```python
from lecture import whiteboard

def main():
    whiteboard("Derivation board", width=1200, height=675, background="grid")
```

This emits a stock v1 component with an **Open Derivation board** button. It works
in reader, presenter and inspector views, including self-contained static HTML.
The React drawing module loads on first open; static exports only
include the engine when a whiteboard is present. No drawing library or extra
Python dependency is required. See [whiteboard.py](../examples/whiteboard.py).

Tools include pressure-sensitive pen, translucent highlighter, whole-stroke
eraser, line, arrow, rectangle, ellipse, text, color/size controls, blank/grid/dot
paper, undo/redo, reversible clear, and full screen. Text is plain text, not TeX.
Native labels and keyboard controls are provided. **Add text at center** supports
keyboard-only annotations; **Board text alternative** lists text and summaries of
the latest 100 objects. Freehand sketches still need an author-provided equivalent
description when they convey essential information.

Pair a Bluetooth pen with the operating system. The board uses standard browser
[Pointer Events](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events),
not Web Bluetooth: it supports devices that the OS/browser exposes as pen or mouse
input. Pressure and the hardware eraser depend on that device/driver mapping.
Touch is ignored by default to reduce palm marks; uncheck the option for finger
drawing. This is not device-level palm rejection. A Bluetooth presentation remote
that only sends buttons cannot supply handwriting coordinates.

Drawings, undo history, and tool settings survive stepping away and back, changing
views, and closing/reopening a board. They are **local viewer annotations**, not
new Python events, shared live state, or an autosaved recording. Reloading loses
unsaved drawings. **Save drawing** exports editable JSON; **Load drawing** restores
it into a board with the same logical width/height (file limit 32 MB). Save SVG for
vector output or PNG for a raster image; each export also exposes a download link.
Browser download behavior can vary in embedded viewers.

To keep memory predictable, boards allow 2,000 objects, 100,000 total points,
10,000 points per stroke, and up to 200 undo commands (also limited by retained
geometry and text size). Lift the pen to begin another
stroke if a stroke reaches its limit. Canvas resolution is capped independently
of display scale; this is a bounded whiteboard, not an infinite-canvas editor.

## Reference browser windows

Use a reference window when a learner should consult an external page alongside the
lecture without embedding or downloading that page:

```python
from lecture import browser_close, browser_open, note

def main():
    browser_open(
        "https://arxiv.org/",
        window_id="paper",
        title="arXiv reference",
        width=1100,
        height=760,
        left=80,
        top=60,
    )
    note("Continue stepping with the reference open; close it when finished.")
    browser_close("paper")
```

`browser_open()` records an intent; it never fetches the URL during authoring or
opens a popup while a bundle is merely loading. Reader, Presenter, and Inspector
render the same accessible control. A user-activated Presenter/Inspector step
transition may apply the recorded open and focus/reuse a named
`lectpy_<window_id>` window. The learner can also use the explicit Open/Focus
button. A later `browser_close()` event closes that viewer-owned window when its
step is reached; the card's Close button is also available. Browsers that block
scripted windows still expose an ordinary `target="_blank"` fallback link.

Only absolute `http://` and `https://` URLs are accepted. Window IDs, titles,
dimensions, and screen positions are bounded at author time and normalized again
by the browser client. Position is a best-effort browser hint, not a guarantee
across operating systems or multi-monitor setups. The page is external to the
lecture: no remote content is copied into the bundle, and authors should not put
secrets or private data in the URL.

The event remains a normal v1 `component` descriptor, so older readers show the
recorded component fallback rather than failing the entire replay. See
[browser_reference.py](../examples/browser_reference.py) for a runnable example.
