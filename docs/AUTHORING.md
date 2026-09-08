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

Primitives: `text`, `code`, `table`, `note`, `image`, `video`, `link`, `plot`, `inspect_value`,
`clear`, `system_text`, `component`, `terminal`. All emit typed events on the
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
