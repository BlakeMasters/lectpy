"""TraceExecutor — edtrace-compatible pedagogical stepper as one provider.

Retains sys.settrace line-stepping + @inspect/@hide/step-over semantics, but
emits the neutral ordered event log on a scoped ExecutionContext instead of a
monolithic JSON trace with eager serialization and a global accumulator.
"""

from __future__ import annotations

import importlib.util
import linecache
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Any

from .artifacts import ArtifactStore
from .context import ExecutionContext, execution_scope
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
    for lineno, text in source_lines.items():
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
        source = path.read_text(encoding="utf-8")
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
            return ctx
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as e:
            ctx.emit("error", {"message": f"import failed: {e!r}"})
            ctx.emit("session_end", {"status": "import-error"})
            sys.modules.pop(module_name, None)
            return ctx

        main = getattr(module, "main", None)
        if not callable(main):
            ctx.emit("error", {"message": "lecture module defines no callable main()"})
            ctx.emit("session_end", {"status": "no-main"})
            sys.modules.pop(module_name, None)
            return ctx

        # Normalize for Windows case/sep comparisons
        target_norm = str(path).lower().replace("/", "\\")

        step_over_lines: set[int] = {ln for ln, d in directives.items() if d.get("step_over")}
        # Standalone `# @clear` comment lines never produce a `line` event
        # (no bytecode). Fire each once when execution next reaches a line at
        # or past it — attached to the following pedagogical step.
        clear_only_lines: list[int] = sorted(
            ln
            for ln, d in directives.items()
            if d.get("clear") and source_lines.get(ln, "").strip().startswith("#")
        )
        state = {
            "depth": 0,
            "no_descend_frames": set(),  # id(frame) that should not emit steps
            "step_over_callers": set(),  # id(frame) whose calls collapse one level
            "nsteps": 0,
            "start": time.time(),
            "pending_clears": set(clear_only_lines),
            "pending_inspects": [],  # names deferred past their assignment line
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

        def tracer(frame: FrameType, event: str, arg: Any) -> Any:
            # Only pedagogically-visible source; never trace stdlib/site-packages.
            filename = frame.f_code.co_filename
            if not _should_trace_file(filename):
                return None
            func = frame.f_code.co_name
            # Decorator-driven hiding / step-over
            if func != "<module>":
                # look up possibly-decorated function object for markers
                target = frame.f_globals.get(func) or getattr(module, func, None)
                if getattr(target, "__lecture_hide__", False):
                    return None
                if event == "call" and getattr(target, "__lecture_step_over__", False):
                    # Collapse the whole call: the call-site line in the
                    # caller is the single pedagogical step; never descend.
                    state["no_descend_frames"].add(id(frame))
                    return None
            if id(frame) in state["no_descend_frames"]:
                return None

            if event == "call":
                state["depth"] += 1
                # If caller line requested step-over, don't descend into this call.
                caller = frame.f_back
                if caller is not None and id(caller) in state["step_over_callers"]:
                    state["no_descend_frames"].add(id(frame))
                    return None
                # comment-driven step-over: check caller line
                try:
                    if caller is not None and caller.f_lineno in step_over_lines:
                        state["no_descend_frames"].add(id(frame))
                        return None
                except Exception:
                    pass
                return tracer
            if event == "return":
                state["depth"] = max(0, state["depth"] - 1)
                state["step_over_callers"].discard(id(frame))
                state["no_descend_frames"].discard(id(frame))
                # Last chance for deferred inspects (e.g. assignment on the
                # final line has no *next* line event; `return` sees post-state).
                if state["pending_inspects"]:
                    still_pending = []
                    for name in state["pending_inspects"]:
                        if name in frame.f_locals:
                            try:
                                ctx.inspect(name, frame.f_locals[name], line=frame.f_lineno)
                            except Exception:
                                pass
                        else:
                            still_pending.append(name)
                    state["pending_inspects"] = still_pending
                return tracer
            if event != "line":
                return tracer

            lineno = frame.f_lineno
            d = directives.get(lineno, {})
            # Flush deferred inspects first: `x = 1  # @inspect x` fires its
            # `line` event *before* the assignment executes, so `x` is only
            # visible on the *next* line event. Same for decorator-requested
            # names on their definition line.
            if state["pending_inspects"]:
                still_pending = []
                for name in state["pending_inspects"]:
                    if name in frame.f_locals:
                        try:
                            ctx.inspect(name, frame.f_locals[name], line=lineno)
                        except Exception:
                            pass
                    else:
                        still_pending.append(name)
                state["pending_inspects"] = still_pending
            # Fire standalone `# @clear` lines reached since the last step.
            for clr in sorted(state["pending_clears"]):
                if clr <= lineno:
                    ctx.emit("clear", {}, line=clr, func=func)
                    state["pending_clears"].discard(clr)
            if d.get("clear") and lineno not in clear_only_lines:
                # Same-line `code  # @clear`: comment-only lines handled above.
                ctx.emit("clear", {}, line=lineno, func=func)
            if d.get("hide"):
                return tracer  # execute but don't record a pedagogical step
            if state["nsteps"] >= self.max_steps:
                raise RuntimeError(f"step budget exceeded ({self.max_steps})")
            if time.time() - state["start"] > self.policy.max_wall_seconds:
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
            ctx.emit(
                "step",
                step_payload,
                line=lineno,
                func=func,
            )
            # comment-driven @inspect names → extra inspect events (lazy handles).
            # Names not yet bound (same-line assignment) defer to the next step.
            for name in d.get("inspect", []):
                if name in frame.f_locals:
                    try:
                        ctx.inspect(name, frame.f_locals[name], line=lineno)
                    except Exception:
                        pass
                elif name not in state["pending_inspects"]:
                    state["pending_inspects"].append(name)
            # decorator-driven @inspect names
            try:
                target = frame.f_globals.get(func) or getattr(module, func, None)
                for name in getattr(target, "__lecture_inspect__", ()) or []:
                    if name in frame.f_locals and name not in d.get("inspect", []):
                        try:
                            ctx.inspect(name, frame.f_locals[name], line=lineno)
                        except Exception:
                            pass
                    elif name not in frame.f_locals and name not in state["pending_inspects"]:
                        state["pending_inspects"].append(name)
            except Exception:
                pass
            self.steps.append(
                TraceStep(
                    seq=len(ctx.log) - 1,
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
                    main()
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
            linecache.clearcache()
            sys.modules.pop(module_name, None)
        return ctx
