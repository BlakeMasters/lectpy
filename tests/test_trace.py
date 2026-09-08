import textwrap

import pytest

from lecture.policy import default_policy
from lecture.trace import TraceExecutor


def _write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    return p


def test_trace_basic_steps_and_outputs(tmp_path):
    src = _write(
        tmp_path,
        "lec.py",
        """
        from lecture import text, inspect_value
        def main():
            text("# Hi")
            x = 1
            inspect_value("x", x)
            y = x + 1
    """,
    )
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(src)
    kinds = [e.kind for e in ctx.log.subscribe()]
    assert "session_start" in kinds and "session_end" in kinds
    assert "text" in kinds and "inspect" in kinds
    assert sum(1 for k in kinds if k == "step") >= 3


def test_trace_hide_and_clear_directives(tmp_path):
    src = _write(
        tmp_path,
        "lec.py",
        """
        from lecture import text
        def main():
            text("before")
            x = 1  # @hide
            # @clear
            y = 2
    """,
    )
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(src)
    kinds = [e.kind for e in ctx.log.subscribe()]
    assert "clear" in kinds
    lines = [e.payload.get("line") for e in ctx.log.subscribe() if e.kind == "step"]
    # the @hide line (x = 1) must not appear as a pedagogical step
    text_src = (tmp_path / "lec.py").read_text().splitlines()
    hide_lineno = next(i + 1 for i, l in enumerate(text_src) if "@hide" in l)
    assert hide_lineno not in lines


def test_trace_inspect_comment(tmp_path):
    src = _write(
        tmp_path,
        "lec.py",
        """
        from lecture import text
        def main():
            w = 2.5  # @inspect w
            w += 1
    """,
    )
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(src)
    inspected = [e for e in ctx.log.subscribe() if e.kind == "inspect"]
    assert any(e.payload.get("name") == "w" for e in inspected)


def test_trace_error_captured_not_raised(tmp_path):
    src = _write(
        tmp_path,
        "lec.py",
        """
        def main():
            raise ValueError("boom")
    """,
    )
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(src)
    kinds = [e.kind for e in ctx.log.subscribe()]
    assert "error" in kinds and "session_end" in kinds


def test_trace_no_main_reports_error(tmp_path):
    src = _write(
        tmp_path,
        "lec.py",
        """
        x = 1
    """,
    )
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(src)
    assert any(e.kind == "error" for e in ctx.log.subscribe())


def test_trace_step_over_decorator_collapses(tmp_path):
    src = _write(
        tmp_path,
        "lec.py",
        """
        from lecture import step_over
        @step_over
        def inner():
            a = 1
            b = 2
            return a + b
        def main():
            x = inner()
    """,
    )
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(src)
    funcs = [e.payload.get("func") for e in ctx.log.subscribe() if e.kind == "step"]
    # inner body lines must not appear as separate steps
    assert "inner" not in funcs


def test_examples_trace_cleanly():
    from pathlib import Path

    ex = Path(__file__).resolve().parents[1] / "examples" / "lecture_01.py"
    ctx = TraceExecutor(policy=default_policy("local-trusted")).trace_file(ex)
    assert any(e.kind == "plot" for e in ctx.log.subscribe())


def test_sdk_outputs_point_to_author_file_line_and_function(tmp_path):
    src = _write(
        tmp_path,
        "locations.py",
        """\
        from lecture import text, note, inspect_value
        def helper():
            text("hello")
            note("note")
            inspect_value("answer", 42)
        def main():
            helper()
    """,
    )
    ctx = TraceExecutor().trace_file(src)
    outputs = [e for e in ctx.log.subscribe() if e.kind in {"text", "note", "inspect"}]
    assert [e.source_location.line for e in outputs] == [3, 4, 5]
    assert all(e.source_location.file == str(src) for e in outputs)
    assert all(e.source_location.func == "helper" for e in outputs)


def test_repeated_traces_reset_step_count(tmp_path):
    src = _write(tmp_path, "repeat.py", "def main():\n    x = 1\n")
    executor = TraceExecutor()
    first = executor.trace_file(src)
    second = executor.trace_file(src)
    assert first.log.to_list()[-1]["payload"]["steps"] == len(executor.steps)
    assert second.log.to_list()[-1]["payload"]["steps"] == len(executor.steps)


@pytest.mark.parametrize("body", ["raise ValueError('import')", "x = 1"])
def test_early_trace_failure_releases_module(tmp_path, body):
    import sys

    before = {k for k in sys.modules if k.startswith("_lecture_target_")}
    ctx = TraceExecutor().trace_file(_write(tmp_path, "failed.py", body))
    assert ctx.log.to_list()[-1]["kind"] == "session_end"
    assert {k for k in sys.modules if k.startswith("_lecture_target_")} == before


def test_budget_exhaustion_still_records_failure_and_end(tmp_path):
    from dataclasses import replace

    policy = replace(default_policy("local-trusted"), max_events=2)
    ctx = TraceExecutor(policy=policy).trace_file(
        _write(tmp_path, "budget.py", "def main():\n    x = 1\n    x += 1\n")
    )
    events = ctx.log.to_list()
    assert [e["kind"] for e in events[-2:]] == ["error", "session_end"]
    assert "event budget exceeded" in events[-2]["payload"]["message"]
