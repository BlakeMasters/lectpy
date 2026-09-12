# Section browser controls

Attach small, explicit Playwright actions to a lecture section. The optional
local runner manages Chromium; the ordinary package and static replay do not
require Playwright or download browsers. Both viewers use the same compact
control strip, loaded only when needed.

## Try the four-scene example

From the repository root, install the optional tools once:

```sh
python -m pip install -e ".[playwright]"
python -m playwright install chromium
```

Build and serve:

```sh
python -m lecture.cli build examples/playwright_controls.py --out var/tmp/browser-lab --view presenter --title "Browser lab"
python -m lecture.cli serve var/tmp/browser-lab --scripts examples/playwright_controls.py --port 8781
```

Open [the local example](http://127.0.0.1:8781/?view=presenter).

1. **Popup:** choose Load experiment, Take step twice, then Capture. Continue
   presenting with the experiment open.
2. **Whiteboard:** choose Work on board. The managed lecture opens its editor,
   places the calculation, draws an underline, inserts a snapshot and closes the
   editor. Reopen it to add your own writing.
3. **Rendered script:** choose Show gradient or Show update. Only that rendered
   code line is highlighted; the Python file is unchanged.
4. **Return:** the popup retains its numerical state. Try Wait, Stop, then another
   step or Capture. Close it and rewind: no script or window-open is replayed.

Scripts operate in the **managed Chromium lecture/window**, not whichever tab
you happened to open first. The original tab can remain a remote control; use
Open / focus to bring the managed target forward. In particular, a whiteboard
in the original tab and one in the managed lecture are independent drawings.
Present from the managed lecture if you want to mix script actions and pen input.
Use Presenter or Inspector with the relevant step selected for lecture-target
actions; Reader view is not a scene-selection interface for scripts.

Add `--headless` for unattended tests. Without `--scripts`, the bundle remains
readable and the controls explain that no runner is connected.

## Authoring

```python
from lecture import section, text
from lecture.browser import PlaywrightControls, browser_script

@browser_script("experiment.next")
async def next_iteration(page):
    await page.get_by_role("button", name="Take step", exact=True).click()
    return "Advanced one iteration"

experiment = PlaywrightControls(
    "experiment",
    url="http://127.0.0.1:9000/experiment",
    actions={"Next iteration": next_iteration},
    viewport=(1000, 700),
)

def main():
    with section("Live experiment", controls=(experiment,)):
        text("Compare the prediction with the next iteration.")
```

Register module-level `async def` functions. Each receives an ordinary async
[Playwright Page](https://playwright.dev/python/docs/pages); it can navigate,
click, type, inspect the DOM or await a result. A returned value becomes status
text. Exceptions and timeouts appear below the controls. Use stable roles/labels
or deliberate output IDs rather than generated CSS or source-line numbers.

Declarations are frozen and support `.with_options(...)`. Nested sections inherit
outer controls. Use `clear()` where you want a new scene instead of cumulative
output. The same control ID reuses its popup and recent captures in later sections;
its target, URL, viewport, actions and timeout must stay consistent. Lifecycle
settings can differ between sections.

| Option | Values / meaning | Default |
| --- | --- | --- |
| `id` | Stable target ID; 1–80 letters, numbers, `.`, `_`, `-` | Required |
| `actions` | Up to 16 button labels mapped to registered async functions | Empty |
| `target` | `popup` or the managed `lecture` | `popup` |
| `url` | Initial popup address, HTTP(S) or `about:blank` | `about:blank` |
| `viewport` | Popup content area, 320–3840 × 180–2160 | `(1000, 700)` |
| `on_enter` | `manual` or `open` on first forward entry to this binding | `manual` |
| `on_leave` | `keep` or `close` when leaving its displayed scope | `keep` |
| `timeout` | Whole-action deadline in seconds, greater than 0 and at most 120 | `15` |

Open / focus, Capture, Stop and Close are built-in. An action creates its target
if necessary; it does not automatically run any other action first. For example,
load the demo before taking its first numerical step. Closing is idempotent.
Reopening a closed popup starts at its configured URL, not its old DOM state.
Popup placement and browser chrome remain OS/browser-controlled; `viewport` is
not an exact desktop-window rectangle. The managed lecture uses 1200 × 850.

## Navigation and execution

- Actions run only from their buttons. Rendering, source selection, reloading
  and backward navigation never run user functions automatically.
- `on_enter="open"` opens/focuses a target once per section binding per viewer
  session, only when stepping forward into it. It does not run an action, open on
  initial load, or repeatedly reopen after a rewind. Open / focus remains explicit.
- `on_leave="close"` closes when step navigation leaves the scope, in either
  direction. A target shared with the next scope is kept open. The managed lecture
  itself can only be closed explicitly. Browser-history navigation and view
  switches do not issue automation commands.
- An action on `target="lecture"` first synchronizes the managed lecture to the
  requesting tab's selected step without reloading. Popup actions do not advance
  the lecture. Manual actions are not an undoable part of the trace.
- One action runs at a time on each target. Stop requests cooperative cancellation;
  completed clicks, typing and drawings are **not undone**. Async scripts should
  yield regularly. Blocking Python or a CPU loop cannot be forcibly interrupted by
  this thread-based first version; a process-isolated worker is not implemented.
  A lifecycle close cancels a running action before closing its window.
- Commands are not retried automatically after a lost response. The runner also
  deduplicates the most recent 256 request IDs.

The runner loads the source module you explicitly name, verifies its hash against
the bundle, and accepts only declared action IDs. Loading still executes normal
module-level Python: keep demonstrations in `main()`, not import-time side effects.
This is trusted local Python execution, not a sandbox. Stop the server to close its
managed browser. Rebuild and restart after changing scripts.

## Addressing rendered code

```python
from lecture import code
from lecture.browser import browser_script, highlight_code

@browser_script("code.update")
async def show_update(page):
    await highlight_code(page, "update", 2)

def main():
    code("gradient = 2 * w\nw -= eta * gradient", "python", output_id="update")
```

Give concurrently visible code blocks unique `output_id` values. Each line gets
`data-code-line="N"` (one-based); the figure has `data-output-id`. The helper
sets `aria-current="true"` on one line and uses the section's highlight color.
This is transient presentation state: navigating away or rerendering the output
clears it. No output ID means no extra per-line markup.

## Captures, exports and React

Capture takes a viewport PNG of the managed target and displays it below the
controls, with Save PNG. The server keeps the latest three captures per control,
at most 8 MB each, in memory. They survive stepping but not a server restart and
are not written into the exported lecture. Whiteboard insertions are separate
viewer-local SVG snapshots; save the drawing or snapshot before reloading.

For React development, serve the same `lecture.json` bundle through its normal
bundle loader and add `?automation=http://127.0.0.1:8781` (or `&automation=...`)
to use this runner. The execution IDs must match. The standalone viewer uses its
same-origin runner; it does not support a separate-origin runner under its CSP.
The local bridge is separate from the general capability broker's live-session API.

## Tests

Normal unit tests need no browser. For the real popup/board/code integration test,
after installing Chromium:

```powershell
$env:LECTPY_BROWSER_TESTS = "1"
python -m pytest tests/test_automation_browser.py
```

Set `LECTPY_BROWSER_ARTIFACTS` to a local directory to retain QA screenshots.
Playwright versions need matching browser binaries; see its
[browser installation guide](https://playwright.dev/python/docs/browsers).
