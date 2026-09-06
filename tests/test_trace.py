import textwrap

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
