"""A reference window that can stay open while a lecture progresses."""

from lecture import browser_close, browser_open, note, text


def main():
    text("# Read alongside the lecture\nOpen the paper reference when you need it.")
    browser_open(
        "https://arxiv.org/",
        window_id="papers",
        title="arXiv reference",
        width=1100,
        height=760,
        left=80,
        top=60,
    )
    note("The reference window is independent: continue stepping with it open.")
    browser_close("papers")
