"""A local, pen-aware whiteboard available in every presentation style."""

from lecture import note, text, whiteboard


def main():
    text("# Work it out together\nSketch a diagram or annotate the derivation.")
    whiteboard("Derivation board", background="grid")
    note("Open the board, pick a tool, and draw. Use Save drawing to keep editable work.")
    whiteboard("Free sketch", width=1000, height=700, background="blank")
