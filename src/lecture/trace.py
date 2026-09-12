"""TraceExecutor — edtrace-compatible pedagogical stepper as one provider.

Retains sys.settrace line-stepping + @inspect/@hide/step-over semantics, but
emits the neutral ordered event log on a scoped ExecutionContext instead of a
monolithic JSON trace with eager serialization and a global accumulator.
"""

from __future__ import annotations

import importlib.util
import inspect
import io
import linecache
import sys
import time
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any

from .artifacts import ArtifactStore
from .context import ExecutionContext, execution_scope
from .events import SourceLocation
from .policy import GrantedPolicy, default_policy

MAX_LOCALS_PER_STEP = 50
MAX_STEPS_DEFAULT = 50_000


@dataclass
class TraceStep:
    seq: int
    file: str
    line: int
    func: str
    locals_summary: dict[str, Any] = field(default_factory=dict)
    reference: dict[str, Any] | None = None
    events_before: int = 0
    events_after: int = 0


def _parse_comment_directives(source_lines: dict[int, str]) -> dict[int, dict[str, Any]]:
    """Parse `# @inspect x,y` / `# @hide` / `# @step-over` / `# @clear` comments."""
    out: dict[int, dict[str, Any]] = {}
    source = "\n".join(source_lines.values()) + "\n"
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):
        return out  # The import/compile path reports the syntax error.
    trivia = {
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.COMMENT,
        tokenize.ENDMARKER,
    }
    next_line = None
    following = {}
    for token in reversed(tokens):
        following[token.start] = next_line
        if token.type not in trivia:
            next_line = token.start[0]
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        lineno, text = token.start[0], token.string
        if not source_lines[lineno][: token.start[1]].strip():
            lineno = following[token.start]
            if lineno is None:
                continue
        low = text.lower()
        if "# @inspect" in low or "# inspect:" in low or "# lectpy: inspect" in low:
            # everything after the marker is a comma/space separated name list
            for marker in ("# @inspect", "# inspect:", "# lectpy: inspect"):
                if marker in low:
                    idx = low.index(marker) + len(marker)
                    rest = text[idx:].strip().lstrip(":").strip()
                    names = [n.strip() for n in rest.replace(",", " ").split() if n.strip()]
                    # filter to valid identifiers to avoid injection into display
                    names = [n for n in names if n.isidentifier()]
                    out.setdefault(lineno, {})["inspect"] = names
                    break
        if "# @hide" in low:
            out.setdefault(lineno, {})["hide"] = True
        if "# @step-over" in low or "# @step_over" in low or "# @stepover" in low:
            out.setdefault(lineno, {})["step_over"] = True
        if "# @clear" in low:
            out.setdefault(lineno, {})["clear"] = True
    return out


class TraceExecutor:
    def __init__(
        self,
        policy: GrantedPolicy | None = None,
        artifacts: ArtifactStore | None = None,
        max_steps: int = MAX_STEPS_DEFAULT,
        *,
        record_steps: bool = True,
    ) -> None:
        self.policy = policy or default_policy("local-trusted")
        self.artifacts = artifacts
        self.max_steps = max_steps
        self.record_steps = record_steps
        self.steps: list[TraceStep] = []

    def trace_file(self, path: str | Path) -> ExecutionContext:
        self.steps.clear()
        path = Path(path).resolve()
        source_bytes = path.read_bytes()
        source = importlib.util.decode_source(source_bytes)
        source_lines = {i + 1: l for i, l in enumerate(source.splitlines())}
        directives = _parse_comment_directives(source_lines)

        ctx = ExecutionContext(source_file=str(path), policy=self.policy, artifacts=self.artifacts)
        ctx.emit(
            "session_start",
            {"source_file": str(path), "runtime": "trace" if self.record_steps else "python"},
        )

        # Load module without executing main yet (mirrors edtrace: import, then trace main()).
        module_name = f"_lecture_target_{ctx.execution_id}"
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            ctx.emit("error", {"message": f"cannot load module: {path}"})
            ctx.emit("session_end", {"status": "import-error"})
            return ctx
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            # Execute the source we just read, not a timestamp/size-matched .pyc
            # left by a rapid edit of the same file.
            exec(compile(source_bytes, str(path), "exec"), module.__dict__)
        except Exception as e:
            ctx.emit("error", {"message": f"import failed: {e!r}"})
            ctx.emit("session_end", {"status": "import-error"})
            sys.modules.pop(module_name, None)
            return ctx
        except BaseException:
            sys.modules.pop(module_name, None)
            raise

        main = getattr(module, "main", None)
        if not callable(main):
            ctx.emit("error", {"message": "lecture module defines no callable main()"})
            ctx.emit("session_end", {"status": "no-main"})
            sys.modules.pop(module_name, None)
            return ctx
        entry = inspect.unwrap(main)
        if any(
            check(entry)
            for check in (
                inspect.iscoroutinefunction,
                inspect.isgeneratorfunction,
                inspect.isasyncgenfunction,
            )
        ):
            ctx.emit(
                "error", {"message": "lecture main() must be synchronous, not async or a generator"}
            )
            ctx.emit("session_end", {"status": "invalid-main"})
            sys.modules.pop(module_name, None)
            return ctx

        # Normalize for Windows case/sep comparisons
        target_norm = str(path).lower().replace("/", "\\")

        step_over_lines: set[int] = {ln for ln, d in directives.items() if d.get("step_over")}
        state = {
            "no_descend_frames": set(),  # actual frames: IDs can be reused by Python
            "nsteps": 0,
            "start": time.monotonic(),
            "pending_inspects": {},  # frame -> names deferred past their assignment line
        }

        def _norm(frame_file: str) -> str:
            return frame_file.lower().replace("/", "\\")

        def _should_trace_file(filename: str) -> bool:
            return (
                _norm(filename) == target_norm
                or _norm(Path(filename).resolve().__str__()) == target_norm
            )

        def _frame_reference(frame: FrameType) -> dict[str, Any] | None:
            """Return the nearest author call site for a nested trace frame."""
            caller = frame.f_back
            while caller is not None:
                caller_file = caller.f_code.co_filename
                if _should_trace_file(caller_file) and caller.f_code.co_name != "<module>":
                    return {
                        "file": str(Path(caller_file).resolve()),
                        "line": int(caller.f_lineno),
                        "func": caller.f_code.co_name,
                    }
                caller = caller.f_back
            return None

        def inspect_local(frame: FrameType, name: str) -> None:
            ctx.inspect(
                name,
                frame.f_locals[name],
                source_location=SourceLocation(str(path), frame.f_lineno, frame.f_code.co_name),
            )

        def tracer(frame: FrameType, event: str, arg: Any) -> Any:
            # Only pedagogically-visible source; never trace stdlib/site-packages.
            filename = frame.f_code.co_filename
            if not _should_trace_file(filename):
                return None
            func = frame.f_code.co_name
            if event == "call":
                target = frame.f_globals.get(func)
                collapsed = getattr(target, "__lecture_hide__", False) or getattr(
                    target, "__lecture_step_over__", False
                )
                # Walk through wrappers/non-author frames as well: descendants
                # of a collapsed helper must stay collapsed until it returns.
                caller = frame.f_back
                while caller is not None:
                    if caller in state["no_descend_frames"] or (
                        _should_trace_file(caller.f_code.co_filename)
                        and caller.f_lineno in step_over_lines
                    ):
                        collapsed = True
                        break
                    caller = caller.f_back
                if collapsed:
                    state["no_descend_frames"].add(frame)
                    frame.f_trace_lines = False
                return tracer
            if frame in state["no_descend_frames"]:
                if event == "return":
                    state["no_descend_frames"].discard(frame)
                return tracer
            if event == "return":
                # Last chance for deferred inspects (e.g. assignment on the
                # final line has no *next* line event; `return` sees post-state).
                pending = state["pending_inspects"].pop(frame, [])
                if pending:
                    for name in pending:
                        if name in frame.f_locals:
                            try:
                                inspect_local(frame, name)
                            except Exception:
                                pass
                return tracer
            if event != "line":
                return tracer

            lineno = frame.f_lineno
            d = directives.get(lineno, {})
            # Flush deferred inspects first: `x = 1  # @inspect x` fires its
            # `line` event *before* the assignment executes, so `x` is only
            # visible on the *next* line event. Same for decorator-requested
            # names on their definition line.
            pending = state["pending_inspects"].pop(frame, [])
            if pending:
                still_pending = []
                for name in pending:
                    if name in frame.f_locals:
                        try:
                            inspect_local(frame, name)
                        except Exception:
                            pass
                    else:
                        still_pending.append(name)
                if still_pending:
                    state["pending_inspects"][frame] = still_pending
            if d.get("clear"):
                ctx.emit("clear", {}, line=lineno, func=func)
            if d.get("hide"):
                return tracer  # execute but don't record a pedagogical step
            if state["nsteps"] >= self.max_steps:
                raise RuntimeError(f"step budget exceeded ({self.max_steps})")
            if time.monotonic() - state["start"] > self.policy.max_wall_seconds:
                raise TimeoutError("trace wall-time budget exceeded")

            # Capture locals summary (truncated; large values get handles on inspect only)
            locals_summary: dict[str, Any] = {}
            try:
                names = list(frame.f_locals.keys())[:MAX_LOCALS_PER_STEP]
                # decorator-requested names first
                target = frame.f_globals.get(func) or getattr(module, func, None)
                extra = list(getattr(target, "__lecture_inspect__", ()) or [])
                for name in extra + d.get("inspect", []):
                    if name in frame.f_locals and name not in names:
                        names.append(name)
                for name in names:
                    try:
                        v = frame.f_locals[name]
                        r = repr(v)
                        locals_summary[name] = r if len(r) <= 500 else r[:500] + "…"
                    except Exception as e:
                        locals_summary[name] = f"<unrepresentable: {e}>"
            except Exception:
                pass

            reference = _frame_reference(frame)
            step_payload: dict[str, Any] = {
                "file": filename,
                "line": lineno,
                "func": func,
                "locals": locals_summary,
            }
            if reference is not None and reference["func"] != func:
                step_payload["ref"] = reference

            seq_before = len(ctx.log)
            step_event = ctx.emit(
                "step",
                step_payload,
                line=lineno,
                func=func,
            )
            # comment-driven @inspect names → extra inspect events (lazy handles).
            # Always observe post-line state, including reassignment of an
            # existing name. Only this frame can satisfy a deferred inspection.
            pending = state["pending_inspects"].setdefault(frame, [])
            for name in d.get("inspect", []):
                if name not in pending:
                    pending.append(name)
            # decorator-driven @inspect names
            try:
                target = frame.f_globals.get(func) or getattr(module, func, None)
                for name in getattr(target, "__lecture_inspect__", ()) or []:
                    if name in frame.f_locals and name not in d.get("inspect", []):
                        try:
                            inspect_local(frame, name)
                        except Exception:
                            pass
                    elif name not in frame.f_locals and name not in pending:
                        pending.append(name)
            except Exception:
                pass
            self.steps.append(
                TraceStep(
                    seq=step_event.seq,
                    file=filename,
                    line=lineno,
                    func=func,
                    locals_summary=locals_summary,
                    reference=reference,
                    events_before=seq_before,
                    events_after=len(ctx.log),
                )
            )
            state["nsteps"] += 1
            return tracer

        old_trace = sys.gettrace()
        if self.record_steps:
            sys.settrace(tracer)
        try:
            with execution_scope(ctx):
                try:
                    result = main()
                    if (
                        inspect.isawaitable(result)
                        or inspect.isgenerator(result)
                        or inspect.isasyncgen(result)
                    ):
                        if inspect.iscoroutine(result) or inspect.isgenerator(result):
                            result.close()
                        raise TypeError(
                            "lecture main() must return synchronously, "
                            "not an awaitable or generator"
                        )
                except Exception as e:
                    import traceback

                    ctx.emit(
                        "error", {"message": f"{e!r}", "traceback": traceback.format_exc()[-4000:]}
                    )
                    ctx.emit("session_end", {"status": "error"})
                else:
                    ctx.emit("session_end", {"status": "ok", "steps": len(self.steps)})
        finally:
            if self.record_steps:
                sys.settrace(old_trace)
            state["pending_inspects"].clear()
            state["no_descend_frames"].clear()
            linecache.clearcache()
            sys.modules.pop(module_name, None)
        return ctx
