import os
import py_compile
import sys
import textwrap

import pytest

from lecture.trace import TraceExecutor


def trace(tmp_path, source):
    path = tmp_path / "edge.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return TraceExecutor().trace_file(path).log.subscribe()


def test_inspect_assignment_uses_post_state_in_its_own_frame(tmp_path):
    events = trace(
        tmp_path,
        """
        def helper():
            x = 999
            return 7
        def main():
            x = helper()  # @inspect x
            x += 1  # @inspect x
    """,
    )
    assert [e.payload["summary"] for e in events if e.kind == "inspect"] == ["7", "8"]


def test_inspect_unknown_name_does_not_escape_its_function(tmp_path):
    events = trace(
        tmp_path,
        """
        def helper():
            pass  # @inspect x
        def main():
            helper()
            x = 999
            return x
    """,
    )
    assert not [e for e in events if e.kind == "inspect"]


def test_inspect_source_location_names_the_actual_helper(tmp_path):
    events = trace(tmp_path, "def helper():\n    x = 1  # @inspect x\ndef main():\n    helper()\n")
    inspection = next(e for e in events if e.kind == "inspect")
    assert inspection.source_location.func == "helper"


@pytest.mark.parametrize("decorator", ["hide", "step_over"])
def test_collapsed_helpers_hide_descendants_but_not_later_calls(tmp_path, decorator):
    events = trace(
        tmp_path,
        f"""
        from lecture import {decorator}, text
        def leaf():
            text("leaf output")
        @{decorator}
        def hidden():
            leaf()
        def visible():
            marker = "visible"
        def main():
            for i in range(4):
                hidden()
                visible()
            leaf()
    """,
    )
    funcs = [e.payload["func"] for e in events if e.kind == "step"]
    assert funcs.count("visible") == 4
    assert funcs.count("leaf") == 1
    assert len([e for e in events if e.kind == "text"]) == 5


def test_directive_text_in_strings_is_not_a_comment(tmp_path):
    events = trace(
        tmp_path,
        """
        from lecture import text
        def main():
            text("literal # @hide")
            text("literal # @clear")
    """,
    )
    assert len([e for e in events if e.kind == "step"]) == 2
    assert not [e for e in events if e.kind == "clear"]


def test_standalone_clear_belongs_to_following_line_on_every_visit(tmp_path):
    events = trace(
        tmp_path,
        """
        from lecture import text
        def helper():
            # @clear
            text("inside")
        def main():
            text("before")
            helper()
            helper()
    """,
    )
    content = [
        e.kind if e.kind == "clear" else e.payload["markdown"]
        for e in events
        if e.kind in {"text", "clear"}
    ]
    assert content == ["before", "clear", "inside", "clear", "inside"]


def test_standalone_step_over_collapses_the_following_call(tmp_path):
    events = trace(
        tmp_path,
        """
        def helper():
            x = 1
        def main():
            # @step-over
            helper()
            helper()
    """,
    )
    assert len([e for e in events if e.kind == "step" and e.payload["func"] == "helper"]) == 1


@pytest.mark.parametrize("prefix", ["async def", "def"])
def test_non_synchronous_main_reports_failure(tmp_path, prefix):
    body = "return 1" if prefix == "async def" else "yield 1"
    events = trace(tmp_path, f"{prefix} main():\n    {body}\n")
    assert events[-1].payload["status"] != "ok"
    assert any(e.kind == "error" and "synchronous" in e.payload["message"] for e in events)


def test_import_system_exit_releases_temporary_module(tmp_path):
    before = {key for key in sys.modules if key.startswith("_lecture_target_")}
    with pytest.raises(SystemExit):
        trace(tmp_path, "raise SystemExit(0)")
    assert {key for key in sys.modules if key.startswith("_lecture_target_")} == before


def test_rapid_same_size_edit_does_not_execute_stale_bytecode(tmp_path):
    path = tmp_path / "cached.py"
    original = 'from lecture import text\ndef main():\n    text("old")\n'
    path.write_text(original, encoding="utf-8")
    stamp = path.stat().st_mtime
    py_compile.compile(str(path))
    path.write_text(original.replace('"old"', '"new"'), encoding="utf-8")
    os.utime(path, (stamp, stamp))
    events = TraceExecutor().trace_file(path).log.subscribe()
    assert [e.payload["markdown"] for e in events if e.kind == "text"] == ["new"]


def test_trace_step_sequence_points_to_step_not_inspection(tmp_path):
    path = tmp_path / "inspection.py"
    path.write_text(
        'from lecture import inspect\n@inspect("x")\ndef main():\n    x = 1\n    x += 1\n',
        encoding="utf-8",
    )
    executor = TraceExecutor()
    events = executor.trace_file(path).log.subscribe()
    assert all(events[step.seq].kind == "step" for step in executor.steps)
