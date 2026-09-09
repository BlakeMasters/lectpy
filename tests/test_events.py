import pytest

from lecture import equation, uml
from lecture.context import ExecutionContext, execution_scope
from lecture.events import EventLog, replay_to_presentation, validate_event


def test_validate_ok():
    d = {
        "session_id": "s",
        "execution_id": "e",
        "seq": 0,
        "kind": "text",
        "payload": {},
        "schema_version": 1,
    }
    assert validate_event(d) == []


def test_validate_rejects_unknown_kind_and_bad_seq():
    assert validate_event({"session_id": "s", "execution_id": "e", "seq": -1, "kind": "nope"}) != []
    assert validate_event({"session_id": "s"}) != []


def test_validate_rejects_non_sha_artifact_ref():
    d = {
        "session_id": "s",
        "execution_id": "e",
        "seq": 0,
        "kind": "text",
        "payload": {},
        "artifact_refs": ["../../etc/passwd"],
    }
    assert any("sha256" in e for e in validate_event(d))


def test_log_monotonic_and_subscribe():
    log = EventLog("s", "e")
    log.append("session_start", {})
    log.append("text", {"markdown": "hi"})
    log.append("step", {"line": 1})
    assert log.check_monotonic()
    assert [e.seq for e in log.subscribe(after_seq=0)] == [1, 2]
    assert [e.seq for e in log.subscribe()] == [0, 1, 2]


def test_log_rejects_unknown_kind():
    log = EventLog("s", "e")
    with pytest.raises(ValueError):
        log.append("teleport", {})


def test_from_list_enforces_monotonic():
    log = EventLog("s", "e")
    log.append("text", {"a": 1})
    items = log.to_list()
    items[0]["seq"] = 5
    with pytest.raises(ValueError):
        EventLog.from_list("s", "e", items)


def test_replay_is_deterministic_and_clear_resets():
    log = EventLog("s", "e")
    log.append("step", {"line": 1})
    log.append("text", {"markdown": "a"})
    log.append("inspect", {"name": "x", "summary": "1"})
    log.append("clear", {})
    log.append("step", {"line": 2})
    log.append("text", {"markdown": "b"})
    items = log.to_list()
    once = replay_to_presentation(items)
    twice = replay_to_presentation(list(items))
    assert once == twice
    assert len(once["steps"]) == 2
    assert [o["markdown"] for o in once["outputs"] if o["kind"] == "text"] == ["b"]
    assert once["inspect_state"] == {}


def test_golden_replay_fixture():
    # Fixed history must always reconstruct the same presentation state.
    events = [
        {
            "session_id": "s",
            "execution_id": "e",
            "seq": 0,
            "kind": "step",
            "payload": {"line": 10, "func": "main"},
            "schema_version": 1,
        },
        {
            "session_id": "s",
            "execution_id": "e",
            "seq": 1,
            "kind": "text",
            "payload": {"markdown": "# T"},
            "schema_version": 1,
        },
        {
            "session_id": "s",
            "execution_id": "e",
            "seq": 2,
            "kind": "inspect",
            "payload": {"name": "w", "summary": "0.0"},
            "schema_version": 1,
        },
        {
            "session_id": "s",
            "execution_id": "e",
            "seq": 3,
            "kind": "step",
            "payload": {"line": 11, "func": "main"},
            "schema_version": 1,
        },
    ]
    pres = replay_to_presentation(events)
    assert len(pres["steps"]) == 2
    assert pres["inspect_state"] == {"w": "0.0"}
    assert pres["outputs"][0]["kind"] == "text"


def test_equation_and_uml_are_first_class_replay_outputs():
    ctx = ExecutionContext()
    with execution_scope(ctx):
        equation(r"x_{t+1} = x_t - \eta g_t", output_id="update")
        uml(
            "class",
            {"classes": [{"name": "Lecture", "methods": ["step()"]}]},
            output_id="lecture-class",
        )
    kinds = [event.kind for event in ctx.log.subscribe()]
    assert kinds == ["equation", "uml"]
    outputs = replay_to_presentation(ctx.log.to_list())["outputs"]
    assert [output["kind"] for output in outputs] == ["equation", "uml"]
    assert outputs[0]["output_id"] == "update"
    assert outputs[1]["uml_kind"] == "class"
