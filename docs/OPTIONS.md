# Presentation options

Start with a preset, then change only what the section needs. No extra packages,
font downloads, global state, or CSS strings are required.

```python
from lecture import section, equation, whiteboard, WhiteboardOptions
from lecture.styles import TECHNICAL, PAPER, SEMINAR

working = PAPER.with_options(width="wide", highlight="violet")
board = WhiteboardOptions(
    background="dots", color="#7c3aed", stroke_width=3,
    insertable=True, close_on_insert=True,
)

def main():
    with section("Derivation", style=working):
        equation(r"w_{t+1} = w_t - \eta\nabla J(w_t)")
        whiteboard("Work it through", options=board)
```

## Section styles

| Starting point | Typography | Spacing / width | Active output |
| --- | --- | --- | --- |
| `TECHNICAL` | Technical sans-serif and code fonts | Compact / wide | Amber left rule |
| `PAPER` | Serif | Comfortable / reading | Light blue wash |
| `SEMINAR` | System, 20% larger | Roomy / full | Light mint wash |

Presets are frozen `PresentationStyle` objects. `.with_options(...)` returns a
validated copy; it never changes the original. `PresentationStyle(...)` creates
your own starting point. Existing `section(..., tone=..., density=...)` calls
continue to work.

| Option | Values | Default |
| --- | --- | --- |
| `tone` | neutral, hero, evidence, code, recap | neutral |
| `density` | compact, comfortable, roomy | comfortable |
| `width` | reading (72ch), wide (96ch), full | reading |
| `align` | start, center | start |
| `font` | viewer, system, technical, reading | viewer |
| `text_size` | normal, large (1.2×) | normal |
| `highlight` | viewer, amber, blue, mint, violet | viewer |
| `focus` | line, wash, none | wash |

`tone` colors the section label; `highlight` colors the active output.
`font="viewer"` and `highlight="viewer"` follow the toolbar choices. Explicit
section choices override the toolbar for those outputs only. Native math fonts
still typeset equations; their surrounding scale/spacing follow the section.
UML diagrams fit their container and retain the renderer's label proportions.

Precedence is **section keywords → explicit style → defaults**. Without an
explicit style, a nested section inherits its enclosing section instead of the
defaults. `None` means “not specified”; use `font="viewer"` or
`highlight="viewer"` to explicitly return control to the toolbar.

```python
with section("Results", style=TECHNICAL):
    # Keeps technical typography and width, but uses a violet focus color.
    with section("A special case", highlight="violet"):
        equation(r"x^2 = 4")
    # Outer settings are restored, including after exceptions.
```

These hints attach to each output, not the whole page. Nothing changes execution
or automatically hides source, opens references, or clears earlier output. Use
`clear()` for an intentional scene boundary. Prior output remains fully legible;
Reader view suppresses active-step highlighting. Both viewers share the same
normalization and section CSS.

## Whiteboard options

`whiteboard(..., options=board, color="#2563eb")` overrides the reusable object's
color for that board. All settings also work directly as keyword arguments.

| Option | Values / limits | Default |
| --- | --- | --- |
| `width`, `height` | Logical pixels: 320–3840, 180–2160 | 1200 × 675 |
| `background` | blank, grid, dots | grid |
| `tool` | pen, highlighter, eraser, line, arrow, rectangle, ellipse, text | pen |
| `color` | Six-digit hex color | #1d4ed8 |
| `stroke_width` | Integer 1–48 | 4 |
| `insertable` | Show Insert snapshot | False |
| `close_on_insert` | Close the editor after inserting; requires insertable | False |

Title, `alt`, and `output_id` belong to the individual output, not the reusable
options. Initial tool/color/width settings do not overwrite a presenter's local
edits when stepping backward and forward.

An inserted snapshot stays below its board and survives replay navigation in the
same viewer session. Reopen the board to keep editing and insert another revision.
Only the most recent 12 snapshots are retained; revision numbers never repeat.
This is local annotation state, not a modification to the Python source or exported
lecture. Reloading loses it: Save SVG/PNG for finished work or Save drawing for the
current editable drawing. Saving a drawing does not save snapshot history.

## Runnable example

From the repository root:

```sh
python -m lecture.cli build examples/presentation_options.py --out var/tmp/options --view presenter
python -m lecture.cli serve var/tmp/options --port 8777
```

Open http://127.0.0.1:8777. Six scenes explain a quadratic optimization problem,
switching between code, equations, an insertable board, a numerical table, and UML.
Each hidden helper in `main()` is one scene, avoiding argument-by-argument trace
steps. The generated bundle is under ignored `var/`; the reusable example is public.

Equations currently support a small TeX subset, not full LaTeX. UML supports
structured class and sequence specifications, not arbitrary PlantUML/Mermaid text.
See [interactive outputs](INTERACTIVE_OUTPUTS.md) for those contracts.

Sections also accept optional `controls=(PlaywrightControls(...),)` for local
browser scripts. See [browser controls](BROWSER_CONTROLS.md) for the runner,
popup lifecycle, whiteboard interaction and rendered-code highlighting example.
