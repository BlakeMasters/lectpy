from lecture import clear, inspect_value, section, text
from lecture.context import ExecutionContext, execution_scope, get_current


def test_scoped_context_isolation():
    ctx_a = ExecutionContext(source_file="a.py")
    ctx_b = ExecutionContext(source_file="b.py")
    with execution_scope(ctx_a):
        text("hello a")
        assert get_current() is ctx_a
    with execution_scope(ctx_b):
        text("hello b")
        assert get_current() is ctx_b
    assert len(ctx_a.log) == 1 and len(ctx_b.log) == 1
    assert ctx_a.log.to_list()[0]["payload"]["markdown"] == "hello a"


def test_nested_scope_restores_outer():
    outer = ExecutionContext()
    inner = ExecutionContext()
    with execution_scope(outer):
        with execution_scope(inner):
            text("in")
        assert get_current() is outer
        text("out")
    assert len(inner.log) == 1 and len(outer.log) == 1


def test_large_value_gets_handle_not_eager_blob():
    ctx = ExecutionContext()
    big = list(range(5000))
    with execution_scope(ctx):
        ev = inspect_value("big", big)
    assert "handle" in ev.payload
    assert ctx.get_object(ev.payload["handle"]) is big
    # event payload stays small
    assert len(str(ev.payload.get("preview", ""))) < 2000


def test_small_value_has_no_handle():
    ctx = ExecutionContext()
    with execution_scope(ctx):
        ev = inspect_value("x", 42)
    assert "handle" not in ev.payload
    assert ev.payload["summary"] == "42"


def test_section_scopes_projection_metadata_without_changing_event_kind():
    with execution_scope() as ctx:
        text("before")
        with section("Evidence", tone="evidence", density="compact", width="wide"):
            text("inside")
        text("after")

    events = ctx.log.subscribe()
    assert "presentation" not in events[0].payload
    assert events[1].payload["presentation"] == {
        "name": "Evidence",
        "tone": "evidence",
        "density": "compact",
        "width": "wide",
        "align": "start",
    }
    assert "presentation" not in events[2].payload


def test_clear_emits_event():
    ctx = ExecutionContext()
    with execution_scope(ctx):
        text("a")
        clear()
    kinds = [e.kind for e in ctx.log.subscribe()]
    assert kinds == ["text", "clear"]
