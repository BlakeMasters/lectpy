"""A Python document: build with --provider python to omit line stepping."""

from lecture import inspect_value, note, text


def main():
    text("# A Python document\n\nCompose explanations and results with ordinary Python.")
    values = [2, 3, 5, 7, 11]
    total = sum(values)
    text(f"The sum of the first five primes is **{total}**.")
    inspect_value("primes", values)
    note("This page can be opened offline. No Python process is needed to read it.")
