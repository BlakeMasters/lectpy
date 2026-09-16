"""Synchronized trajectory and response playback in plain Python."""

import math

from lecture import step_keyables, step_playback, text


def state_at(progress: float, method: str) -> dict[str, float]:
    if method == "smooth":
        return {
            "x": 0.25 + 1.50 * (1 - math.exp(-4.6 * progress)),
            "y": 0.58 + 0.84 * (1 - math.exp(-3.4 * progress)),
        }
    return {
        "x": 0.25
        + 1.50 * (1 - math.exp(-3.15 * progress))
        + 0.09 * math.sin(8 * math.pi * progress) * math.exp(-3.5 * progress),
        "y": 0.58
        + 0.84 * (1 - math.exp(-3.0 * progress))
        - 0.10 * math.sin(6 * math.pi * progress) * math.exp(-3.0 * progress),
    }


def main() -> None:
    steps = 40
    smooth_path = []
    adaptive_path = []
    activation = []
    ringdown = []
    adjoint = []

    for step in range(steps + 1):
        progress = step / steps
        smooth_path.append(state_at(progress, "smooth"))
        adaptive_path.append(state_at(progress, "adaptive"))
        activation.append(
            0.42 * (1 - math.exp(-5.4 * progress))
            + 0.012 * math.sin(12 * math.pi * progress) * math.exp(-5 * progress)
        )
        ringdown.append(0.18 * math.sin(8 * math.pi * progress) * math.exp(-2.35 * progress))
        adjoint.append(
            0.52 * (1 - math.exp(-5.1 * progress))
            + 0.15 * math.sin(6 * math.pi * progress) * math.exp(-2.25 * progress)
        )

    text("# Damped adaptation\n\nThe trajectory and response curves share one playback clock.")
    step_playback(
        {
            "x_label": "w₁",
            "y_label": "w₂",
            "series": [
                {"id": "smooth", "label": "smooth path", "points": smooth_path},
                {"id": "adaptive", "label": "adaptive path", "points": adaptive_path},
            ],
            "contours": [
                {"level": level, "dashed": level == 0.90}
                for level in (0.30, 0.46, 0.66, 0.90, 1.20, 1.58, 2.05)
            ],
            "target": {
                "x": smooth_path[-1]["x"], "y": smooth_path[-1]["y"], "label": "equilibrium"
            },
        },
        [
            {
                "id": "activation",
                "title": "Activation",
                "y_label": "Δhₜ − h₀",
                "series": [
                    {"id": "activation", "label": "activation", "values": activation},
                    {"id": "ringdown", "label": "damped response", "values": ringdown},
                ],
                "references": [
                    {"value": 0.42, "label": "equilibrium", "tone": "series-1"},
                    {"value": 0.0, "label": "baseline", "tone": "muted"},
                ],
            },
            {
                "id": "adjoint",
                "title": "Adjoint",
                "y_label": "λₜ",
                "series": [{"id": "adjoint", "label": "settling adjoint", "values": adjoint}],
                "references": [{"value": 0.52, "label": "long-run λ∞", "tone": "series-2"}],
            },
        ],
        title="Damped adaptation",
        alt=(
            "A synchronized forty-step playback comparing two state-space paths "
            "with activation and adjoint response curves."
        ),
        output_id="damped-adaptation",
        autoplay_on_step=True,
        restart_on_enter=True,
        pause_on_leave=True,
        keyables={
            "ArrowUp": {"action": "playback.play", "label": "Play playback"},
            "ArrowDown": {"action": "playback.pause", "label": "Pause playback"},
            "Space": {"action": "playback.toggle", "label": "Toggle playback"},
            "Shift+ArrowRight": {"action": "step.next", "label": "Advance lecture"},
        },
    )
    with step_keyables({
        "Shift+ArrowRight": {"action": "step.next", "label": "Advance lecture"},
    }):
        text("Keyboard: ↑ play or resume · ↓ pause · Space toggle · Shift+→ advance lecture.")
