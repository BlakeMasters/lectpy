import json

import pytest

from lecture import component, step_keyables, step_playback
from lecture.context import ExecutionContext, execution_scope
from lecture.export_static import export_static
from lecture.ir import LectureManifest


def playback_spec():
    return (
        {
            "x_label": "w₁",
            "y_label": "w₂",
            "series": [
                {"id": "path", "label": "path", "points": [(0.2, 0.5), (0.7, 0.9), (1.0, 1.1)]}
            ],
            "target": {"x": 1.0, "y": 1.1, "label": "equilibrium"},
        },
        [
            {
                "title": "Activation",
                "y_label": "Δhₜ",
                "series": [{"id": "activation", "label": "activation", "values": [0.0, 0.2, 0.3]}],
                "references": [{"value": 0.3, "label": "equilibrium", "tone": "series-1"}],
            }
        ],
    )


def test_step_playback_normalizes_bounded_props_and_infers_steps():
    ctx = ExecutionContext()
    with execution_scope(ctx):
        event = step_playback(*playback_spec(), title="Demo", output_id="demo")

    props = event.payload["props"]
    assert event.kind == "component"
    assert event.payload["component_type"] == "step-playback"
    assert props["step_count"] == 2
    assert props["trajectory"]["series"][0]["points"][0] == {"x": 0.2, "y": 0.5}
    assert props["output_id"] == "demo"


def test_step_playback_rejects_mismatched_sample_counts():
    trajectory, responses = playback_spec()
    trajectory["series"].append({"label": "short", "points": [(0, 0), (1, 1)]})
    ctx = ExecutionContext()
    with execution_scope(ctx), pytest.raises(ValueError, match="same sample count"):
        step_playback(trajectory, responses)


def test_step_playback_rejects_response_count_mismatch():
    trajectory, responses = playback_spec()
    responses[0]["series"][0]["values"] = [0.0, 0.2]
    ctx = ExecutionContext()
    with execution_scope(ctx), pytest.raises(ValueError, match=r"step_count \+ 1"):
        step_playback(trajectory, responses)


def test_step_playback_adds_step_trigger_and_merges_scoped_keyables():
    ctx = ExecutionContext()
    with execution_scope(ctx):
        with step_keyables({"Shift+ArrowRight": {"action": "step.next", "label": "Advance"}}):
            event = step_playback(
                *playback_spec(),
                output_id="demo",
                autoplay_on_step=True,
                restart_on_enter=True,
                pause_on_leave=True,
                keyables={"ArrowDown": "playback.pause"},
            )

    assert event.payload["props"]["step_trigger"] == {
        "autoplay_on_step": True,
        "restart_on_enter": True,
        "pause_on_leave": True,
    }
    bindings = {entry["key"]: entry for entry in event.payload["step_keyables"]}
    assert bindings["ArrowDown"]["action"] == "playback.pause"
    assert bindings["ArrowDown"]["target"] == "demo"
    assert bindings["Shift+ArrowRight"]["action"] == "step.next"


def test_step_keyables_scope_attaches_to_arbitrary_events():
    ctx = ExecutionContext()
    with execution_scope(ctx), step_keyables({"ArrowDown": "playback.pause"}):
        event = component("custom-figure", props={"output_id": "figure"})

    assert event.payload["step_keyables"][0]["action"] == "playback.pause"


def test_keyable_aliases_override_scopes_and_scope_restores_after_error():
    ctx = ExecutionContext()
    with execution_scope(ctx), step_keyables({"Control+Shift+p": "step.next"}):
        with pytest.raises(RuntimeError), step_keyables({"Shift+Ctrl+P": "playback.pause"}):
            event = component("figure")
            assert event.payload["step_keyables"][0]["action"] == "playback.pause"
            raise RuntimeError("leave scope")
        restored = component("figure")
        explicit = component("figure", keyables={"ctrl+shift+p": "playback.play"})
    assert restored.payload["step_keyables"][0]["action"] == "step.next"
    assert explicit.payload["step_keyables"] == [{
        "key": "Ctrl+Shift+p", "action": "playback.play",
        "label": "playback play", "prevent_default": True,
    }]


@pytest.mark.parametrize("key", ["Typo+ArrowRight", "Ctrl+Control+p", "Shift+"])
def test_keyables_reject_invalid_modifiers(key):
    with execution_scope(ExecutionContext()), pytest.raises(ValueError):
        with step_keyables({key: "step.next"}):
            pass


def test_keyable_limit_applies_after_merging_scopes_and_explicit_bindings():
    ctx = ExecutionContext()
    with execution_scope(ctx), step_keyables({f"F{i}": "step.next" for i in range(1, 13)}):
        with pytest.raises(ValueError, match="merged bindings"):
            with step_keyables({"ArrowDown": "pause"}):
                pass
        with pytest.raises(ValueError, match="merged bindings"):
            component("figure", keyables={"ArrowDown": "pause"})
        assert len(component("figure").payload["step_keyables"]) == 12


def test_static_export_mounts_step_playback_renderer(tmp_path):
    ctx = ExecutionContext()
    with execution_scope(ctx):
        step_playback(*playback_spec())

    out = export_static(ctx, LectureManifest(title="Playback"), tmp_path / "bundle")
    html = (out / "index.html").read_text(encoding="utf-8")
    bundle = json.loads((out / "lecture.json").read_text(encoding="utf-8"))
    assert "data-step-playback" in html
    assert "data-step-keyables" in html
    assert "lectpy:step-playback-control" in html
    assert "mountStepPlayback" in html
    assert bundle["events"][0]["payload"]["component_type"] == "step-playback"
