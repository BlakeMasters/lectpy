"""Processes, components, and directives — lectpy Level B preview."""
from lecture import component, hide, inspect, note, system_text, terminal, text


@hide
def helper(x: float) -> float:
    return x * x


@inspect("total")
def accumulate(vals):
    total = 0.0
    for v in vals:  # @step-over
        total += helper(v)
    return total


def main():
    text("# Beyond tracing\n\nDirectives, brokered processes, and component stubs.")
    x = 3  # @inspect x
    y = helper(x)  # @hide
    # @clear
    note("State cleared above; stepping continues.")
    vals = [1.0, 2.0, 3.0]
    total = accumulate(vals)
    note(f"accumulated total inspection happens via decorator: {total}")
    system_text(["python", "--version"])
    terminal(["python", "examples/lecture_01.py"], mode="recorded")
    component("optimizer-explorer", props={"initial_w": 0.5},
              permissions={"network": [], "kernel": ["python:call:simulate"]})
