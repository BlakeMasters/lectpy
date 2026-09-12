"""Reusable, immutable authoring options; no renderer or optional dependencies."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal


@dataclass(frozen=True)
class PresentationStyle:
    """Section defaults. ``viewer`` leaves fonts/highlight under viewer control."""

    tone: Literal["neutral", "hero", "evidence", "code", "recap"] = "neutral"
    density: Literal["compact", "comfortable", "roomy"] = "comfortable"
    width: Literal["reading", "wide", "full"] = "reading"
    align: Literal["start", "center"] = "start"
    font: Literal["viewer", "system", "technical", "reading"] = "viewer"
    text_size: Literal["normal", "large"] = "normal"
    highlight: Literal["viewer", "amber", "blue", "mint", "violet"] = "viewer"
    focus: Literal["line", "wash", "none"] = "wash"

    def __post_init__(self) -> None:
        choices = {
            "tone": ("neutral", "hero", "evidence", "code", "recap"),
            "density": ("compact", "comfortable", "roomy"),
            "width": ("reading", "wide", "full"),
            "align": ("start", "center"),
            "font": ("viewer", "system", "technical", "reading"),
            "text_size": ("normal", "large"),
            "highlight": ("viewer", "amber", "blue", "mint", "violet"),
            "focus": ("line", "wash", "none"),
        }
        for name, allowed in choices.items():
            if getattr(self, name) not in allowed:
                raise ValueError(f"section {name} must be one of {allowed}")

    def with_options(self, **overrides: Any) -> PresentationStyle:
        """Return a validated copy, leaving this style unchanged."""
        return replace(self, **overrides)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class WhiteboardOptions:
    """Initial board settings; local viewer edits take precedence on replay."""

    width: int = 1200
    height: int = 675
    background: Literal["blank", "grid", "dots"] = "grid"
    insertable: bool = False
    tool: Literal[
        "pen", "highlighter", "eraser", "line", "arrow", "rectangle", "ellipse", "text"
    ] = "pen"
    color: str = "#1d4ed8"
    stroke_width: int = 4
    close_on_insert: bool = False

    def __post_init__(self) -> None:
        for name, minimum, maximum in (
            ("width", 320, 3840),
            ("height", 180, 2160),
            ("stroke_width", 1, 48),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(
                    f"whiteboard {name} must be an integer from {minimum} to {maximum}"
                )
        if self.background not in ("blank", "grid", "dots"):
            raise ValueError("whiteboard background must be blank, grid, or dots")
        if self.tool not in (
            "pen",
            "highlighter",
            "eraser",
            "line",
            "arrow",
            "rectangle",
            "ellipse",
            "text",
        ):
            raise ValueError("whiteboard tool must be a built-in drawing tool")
        if not isinstance(self.color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", self.color):
            raise ValueError("whiteboard color must be a six-digit hex color, such as #1d4ed8")
        for name in ("insertable", "close_on_insert"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"whiteboard {name} must be a bool")
        if self.close_on_insert and not self.insertable:
            raise ValueError("whiteboard close_on_insert requires insertable=True")

    def with_options(self, **overrides: Any) -> WhiteboardOptions:
        return replace(self, **overrides)

    def to_props(self) -> dict[str, Any]:
        # Keep legacy/default payloads small and unchanged for older consumers.
        defaults = WhiteboardOptions()
        return {
            key: value
            for key, value in asdict(self).items()
            if key in ("width", "height", "background") or value != getattr(defaults, key)
        }
