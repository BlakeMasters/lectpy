"""Starting points, not themes: copy and combine with section keyword overrides."""

from .options import PresentationStyle

TECHNICAL = PresentationStyle(
    density="compact",
    width="wide",
    font="technical",
    highlight="amber",
    focus="line",
)
PAPER = PresentationStyle(font="reading", highlight="blue", focus="wash")
SEMINAR = PresentationStyle(
    density="roomy",
    width="full",
    font="system",
    text_size="large",
    highlight="mint",
)
