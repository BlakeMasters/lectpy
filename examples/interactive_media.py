"""Equation → whiteboard → UML example for the built-in viewers.

Build it from the repository root with:

    python -m lecture.cli build examples/interactive_media.py \
        --out var/tmp/interactive-media --provider trace --view presenter \
        --title "Interactive media"

The whiteboard is deliberately insertable: open it, draw with a mouse or
Bluetooth pen, then choose Insert snapshot. The inserted SVG remains visible
below the board while stepping and is backed by the editable drawing state.
"""

from lecture import equation, inspect_value, section, text, uml, whiteboard


def main() -> None:
    with section("The update rule", tone="hero", density="roomy", width="reading", align="center"):
        text(
            "# A small model, made visible\n"
            "We will turn the gradient update into three connected views."
        )
        equation(
            r"\theta_{t+1} = \theta_t - \eta \nabla_\theta J(\theta_t)",
            title="Gradient descent update",
            alt=(
                "The next parameter vector equals the current vector minus the "
                "learning rate times the gradient of the objective."
            ),
            output_id="gradient-update",
        )

    with section("Work it by hand", tone="code", density="comfortable", width="wide"):
        text(
            "## The presenter can pause here\n"
            "Open the board, annotate the terms, and commit the finished derivation."
        )
        equation(
            r"J(\theta) = \frac{1}{m}\sum_{i=1}^{m} \ell(f_\theta(x_i), y_i)",
            title="Objective over a batch",
            output_id="batch-objective",
        )
        whiteboard(
            "Derive the update",
            width=1200,
            height=675,
            background="grid",
            insertable=True,
            output_id="gradient-derivation",
            alt=("Presenter derivation of the gradient update with terms labeled on a grid."),
        )

    with section("Where the pieces live", tone="evidence", density="compact", width="wide"):
        text(
            "## Same idea, different lens\n"
            "The diagrams are structured data, so they remain readable to alternate renderers."
        )
        uml(
            "class",
            {
                "classes": [
                    {
                        "name": "Lecture",
                        "attributes": ["events: EventLog"],
                        "methods": ["step()", "render()"],
                    },
                    {
                        "name": "Equation",
                        "attributes": ["tex: str", "alt: str"],
                        "methods": ["to_mathml()"],
                    },
                    {
                        "name": "Whiteboard",
                        "attributes": ["drawing: Drawing"],
                        "methods": ["commit()", "export_svg()"],
                    },
                    {"name": "UML", "attributes": ["spec: dict"], "methods": ["to_svg()"]},
                ],
                "relations": [
                    {
                        "from": "Lecture",
                        "to": "Equation",
                        "label": "emits",
                        "kind": "association",
                    },
                    {
                        "from": "Lecture",
                        "to": "Whiteboard",
                        "label": "opens",
                        "kind": "association",
                    },
                    {"from": "Lecture", "to": "UML", "label": "renders", "kind": "dependency"},
                ],
            },
            title="Output components",
            alt=(
                "A Lecture emits an Equation, opens a Whiteboard, and renders UML as a dependency."
            ),
            output_id="output-components",
        )
        uml(
            "sequence",
            {
                "participants": ["Presenter", "Lecture", "Whiteboard"],
                "messages": [
                    {"from": "Presenter", "to": "Lecture", "label": "step forward"},
                    {"from": "Lecture", "to": "Whiteboard", "label": "open board"},
                    {"from": "Presenter", "to": "Whiteboard", "label": "draw + Insert snapshot"},
                    {
                        "from": "Whiteboard",
                        "to": "Lecture",
                        "label": "commit SVG",
                        "kind": "return",
                    },
                ],
            },
            title="Interactive derivation sequence",
            alt=(
                "Presenter steps the lecture, the lecture opens a whiteboard, "
                "and the presenter commits an SVG snapshot back to the lecture."
            ),
            output_id="derivation-sequence",
        )

    with section("Presenter handoff", tone="recap", density="roomy", width="reading"):
        result = {"eta": 0.1, "step": "commit"}
        inspect_value("handoff", result)
        text(
            "### What to try\n"
            "1. Step to the board. 2. Draw or add a text label. 3. Insert snapshot. "
            "4. Step through the UML views."
        )
