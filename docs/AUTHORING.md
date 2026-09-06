# Authoring — plain Python lectures

Level A (no frontend code):

```python
from lecture import text, note, inspect_value, plot

def main():
    text("# Gradient descent\nStepping shows live state.")
    w = 0.0
    inspect_value("w", w)
    for i in range(5):
        w -= 0.1 * (2 * w)
        inspect_value("w", w)
    plot({"data": {"values": [{"x": 1, "y": 2}]}, "mark": "line",
          "encoding": {"x": {"field": "x"}, "y": {"field": "y"}}})
```

Primitives: `text`, `note`, `image`, `video`, `link`, `plot`, `inspect_value`,
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

Advanced config lives in `lecture.toml`, not per-call:

```toml
[lecture]
format-version = 1

[runtimes.python]
provider = "trace"   # or "jupyter" (v0.3+)

[policy.default]
network = "deny"
process = "sandbox"

[export.static]
interactive-fallback = "recorded"
```

Levels: **A** pure Python → **B** Python + stock components (sliders, plots,
terminals, quizzes) → **C** custom TS/Web-Component plugin (full SDK + dev
server, v0.4+).
