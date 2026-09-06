"""Gradient descent in plain Python — lectpy basics (Level A authoring)."""
from lecture import inspect_value, note, plot, text


def grad(w: float) -> float:
    return 2 * w


def main():
    text("# Gradient descent\n\nExecutable narrative: step with `←`/`→`, state stays visible.")
    w = 0.0  # @inspect w
    inspect_value("w", w)
    history = []
    for step in range(5):
        w -= 0.1 * grad(w)
        history.append({"step": step, "w": round(w, 4)})
        inspect_value("w", w)
    plot(
        {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": history},
            "mark": "line",
            "encoding": {"x": {"field": "step", "type": "quantitative"}, "y": {"field": "w", "type": "quantitative"}},
        }
    )
    note("Static export keeps this replayable with recorded fallbacks.")
