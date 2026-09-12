"""Six deliberately paced scenes: technical notes → paper → board → seminar.

From the repository root:
    python -m lecture.cli build examples/presentation_options.py \
        --out var/tmp/options --view presenter
    python -m lecture.cli serve var/tmp/options --port 8777

Helpers are hidden from line stepping so each call in main is one scene.
Options are ordinary immutable Python objects, not global viewer configuration.
"""

from lecture import (
    WhiteboardOptions,
    clear,
    code,
    equation,
    hide,
    section,
    table,
    text,
    uml,
    whiteboard,
)
from lecture.styles import PAPER, SEMINAR, TECHNICAL

WORKING = PAPER.with_options(width="wide", highlight="violet")
BOARD = WhiteboardOptions(
    width=1000,
    height=440,
    background="dots",
    color="#7c3aed",
    stroke_width=3,
    insertable=True,
    close_on_insert=True,
)


@hide
def problem():
    clear()
    with section("01 / Technical — compact, amber rule", style=TECHNICAL):
        text("# Minimize a quadratic\nA one-parameter model makes the update easy to inspect.")
        equation(r"J(w) = (w - 3)^2", alt="The objective is w minus three, squared.")
        code("w = 0.0\neta = 0.25\ngradient = 2 * (w - 3)\nw = w - eta * gradient", "python")
        text("The minimum is at **w = 3**. We start at zero and move along the negative gradient.")


@hide
def derivation():
    clear()
    with section("02 / Paper — serif, blue wash", style=PAPER):
        text("# Write down the update")
        equation(r"w_{t+1} = w_t - \eta\, 2(w_t - 3)", title="Gradient descent")
        equation(r"w_1 = 0 - \frac{1}{4}(-6) = 1.5", title="One numerical step")
        # Nested section inherits the paper typography; only emphasis changes.
        with section("Interpretation", focus="none"):
            text(
                "The step halves the distance to the minimum. No highlight is needed for this note."
            )


@hide
def working_board():
    clear()
    with section("03 / Custom paper — violet, wide", style=WORKING):
        text("# Work the next step by hand")
        equation(r"w_2 = 1.5 - \frac{1}{4}\,2(1.5 - 3) = ?")
        whiteboard(
            "Quadratic working",
            options=BOARD,
            output_id="quadratic-working",
            alt="Hand-worked second update: 1.5 plus 0.75 equals 2.25.",
        )
        text(
            "Open the board. Write or type the calculation, then **Insert snapshot**. "
            "The board closes and the finished work stays here. Go forward and back to revisit it."
        )


@hide
def evidence():
    clear()
    with section("04 / Technical — compact evidence", style=TECHNICAL, tone="evidence"):
        text("# Check the sequence")
        table(
            [{"t": t, "w": 3 * (1 - 0.5**t), "J(w)": 9 * 0.25**t} for t in range(5)],
            title="Each update halves the parameter error",
        )
        equation(r"w_t - 3 = (1 - 2\eta)^t(w_0 - 3)")
        text(
            "For this objective, **0 < η < 1** makes the error shrink. "
            "At η = ¼ the convergence is monotone; larger steps can oscillate."
        )


@hide
def sequence():
    clear()
    with section("05 / Seminar — larger type, mint", style=SEMINAR):
        text("# Separate the model from its optimizer")
        uml(
            "sequence",
            {
                "participants": ["Trainer", "Model", "Optimizer"],
                "messages": [
                    {"from": "Trainer", "to": "Model", "label": "gradient(w)"},
                    {"from": "Model", "to": "Trainer", "label": "2(w - 3)", "kind": "return"},
                    {"from": "Trainer", "to": "Optimizer", "label": "step(w, gradient)"},
                    {"from": "Optimizer", "to": "Trainer", "label": "updated w", "kind": "return"},
                ],
            },
            title="One training iteration",
            alt="Trainer requests a gradient from Model, "
            "then asks Optimizer to update w. Both return their results to Trainer.",
        )


@hide
def recap():
    clear()
    with section(
        "06 / Seminar — centered recap, no focus mark", style=SEMINAR, align="center", focus="none"
    ):
        text("# One objective. Three presentation styles.")
        equation(r"w_t \to 3\qquad J(w_t) \to 0")
        text(
            "**Technical** for code and measurements · **Paper** for derivations · "
            "**Seminar** for room-scale explanation"
        )
        text(
            "Styles only affect presentation. The same equation, table, UML and whiteboard "
            "APIs work in every section. Source remains available when you need it."
        )


def main():
    # Trace pauses before a call. Prime the opening, then pause once per scene.
    problem()  # @hide
    derivation()
    working_board()
    evidence()
    sequence()
    recap()
    return  # Keep the recap separate from the preceding scene.
