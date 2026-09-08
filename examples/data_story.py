"""Build with --provider python for a small, offline data story."""

from lecture import code, note, table, text


def main():
    text("# Comparing learning rates\n\nA compact numerical experiment with inspectable results.")
    code(
        "w = 1.0\nfor step in range(6):\n    w -= learning_rate * 2 * w",
        language="python",
        title="The update rule",
    )
    records = []
    for learning_rate in (0.05, 0.1, 0.25):
        w = 1.0
        for step in range(6):
            w -= learning_rate * 2 * w
            records.append(
                {
                    "Learning rate": learning_rate,
                    "Step": step + 1,
                    "Weight": round(w, 6),
                    "Loss": round(w * w, 6),
                }
            )
    table(records, title="Optimizer results")
    text("## Working with larger data\n\nA table can preview a generator without exhausting it.")
    table(
        ({"Sample": i, "Value": i * i} for i in range(100_000)),
        title="A bounded preview of 100,000 records",
        max_rows=5,
    )
    note("Change the Python parameters and rebuild to compare another experiment.")
