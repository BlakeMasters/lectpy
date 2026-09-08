"""Local media is captured relative to this source file, not the process cwd."""

from lecture import asset, image, link, note, text


def main():
    text("# A portable media story\nLocal figures travel with the lecture.")
    figure = asset("assets/pipeline.svg")
    image(
        figure,
        alt="Python source becomes recorded events, then a portable bundle.",
        title="One asset, reused without duplicating the bytes",
    )
    link(figure, "Open the original diagram")
    note("Copy the entire output directory to move the lecture and its media together.")
