# Interactive outputs

The built-in presentation primitives keep author data separate from viewer
markup. Equations retain TeX and render to native MathML; UML retains a small
structured class/sequence spec and renders to accessible SVG. Both viewers
ship the same dependency-free renderers, so a static bundle works offline.

Build the example with the trace provider when you want stepping:

```text
python -m lecture.cli build examples/interactive_media.py --out var/tmp/interactive-media --provider trace --view presenter
```

```python
from lecture import equation, section, uml, whiteboard

with section("Derivation", tone="code"):
    equation(
        r"\theta_{t+1} = \theta_t - \eta \nabla_\theta J(\theta_t)",
        alt="The next parameter vector is the current vector minus the learning rate times the objective gradient.",
        output_id="update-rule",
    )
    whiteboard(
        "Work this out",
        insertable=True,
        output_id="update-work",
        alt="A presenter derivation of the update rule.",
    )

uml(
    "class",
    {
        "classes": [
            {"name": "Lecture", "methods": ["step()", "render()"]},
            {"name": "Equation", "attributes": ["tex: str"]},
        ],
        "relations": [{"from": "Lecture", "to": "Equation", "label": "emits"}],
    },
)
```

An insertable board is a local presenter action. `Insert snapshot` records a
bounded in-view revision with editable drawing data, an SVG rendering, and an
alt description. It survives stepping within that viewer session; use `Save
drawing` or `Save SVG` when the artifact must survive a reload. The immutable
lecture event log is not silently rewritten by a presenter click.

The current renderer intentionally supports a compact TeX subset (`\\frac`,
`\\sqrt`, Greek letters, common operators, scripts, and text commands) and
structured UML class/sequence diagrams. Unsupported TeX remains readable in
the stored event and can be handed to a richer optional renderer later.
