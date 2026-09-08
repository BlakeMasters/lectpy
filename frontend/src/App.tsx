/** lectpy browser shell v0.2.
 *
 *  Loads a v1 lecture bundle (static `lecture.json` today; broker event
 *  subscription in v0.3) and renders the debugger-like lecture view:
 *  step bar, environment inspector, renderer-registry outputs, virtualized
 *  source pane. All stepping is keyboard reachable and URL deep-linked.
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  EnvInspector,
  InspectsList,
  OutputView,
  SourcePane,
  StepBar,
  stepIndexForLine,
} from "./components";
import { readLiveParams } from "./liveParams";
import type { LectureBundle, LectureEvent } from "./protocol";
import {
  ComponentBlock,
  ErrorBlock,
  ImageBlock,
  LinkBlock,
  NoteBlock,
  PlotBlock,
  TerminalBlock,
  TextBlock,
  VideoBlock,
} from "./renderers";
import { CommandRegistry, ExecutionRegistry, RendererRegistry } from "./registry";
import {
  clampStep,
  parseStepParam,
  stepEvents,
  visibleInspects,
  visibleOutputs,
} from "./select";

const LivePanel = lazy(() => import("./LivePanel"));

function buildRegistries() {
  const renderers = new RendererRegistry();
  const opts = { trusted: true };
  renderers.register({ kinds: ["text"], component: TextBlock, ...opts });
  renderers.register({ kinds: ["note"], component: NoteBlock, ...opts });
  renderers.register({ kinds: ["image"], component: ImageBlock, ...opts });
  renderers.register({ kinds: ["video"], component: VideoBlock, ...opts });
  renderers.register({ kinds: ["link"], component: LinkBlock, ...opts });
  renderers.register({ kinds: ["plot"], component: PlotBlock, ...opts });
  renderers.register({ kinds: ["terminal"], component: TerminalBlock, ...opts });
  renderers.register({ kinds: ["component"], component: ComponentBlock, ...opts });
  renderers.register({ kinds: ["error"], component: ErrorBlock, ...opts });

  const commands = new CommandRegistry();
  const executions = new ExecutionRegistry();
  executions.register({ id: "trace", displayName: "Python trace" });
  return { renderers, commands, executions };
}

function bundleUrl(): string {
  const param = new URLSearchParams(window.location.search).get("bundle");
  return param ?? `${import.meta.env.BASE_URL}sample/lecture.json`;
}

export default function App() {
  const regs = useMemo(buildRegistries, []);
  const [bundle, setBundle] = useState<LectureBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [liveLabel, setLiveLabel] = useState<string | null>(null);
  const liveMode = useMemo(
    () => new URLSearchParams(window.location.search).get("live") === "1",
    [],
  );
  const liveInitial = useMemo(() => (liveMode ? readLiveParams() : null), [liveMode]);

  useEffect(() => {
    if (liveMode) {
      setBundle({
        manifest: { format_version: 1, title: "Live lecture", source_file: "", source_sha256: "" },
        events: [],
      });
      return;
    }
    let cancelled = false;
    fetch(bundleUrl())
      .then((r) => {
        if (!r.ok) throw new Error(`bundle fetch failed: ${r.status}`);
        return r.json() as Promise<LectureBundle>;
      })
      .then((b) => {
        if (cancelled) return;
        setBundle(b);
        setIdx(parseStepParam(window.location.search, stepEvents(b.events).length));
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [liveMode]);

  const steps: LectureEvent[] = useMemo(
    () => (bundle ? stepEvents(bundle.events) : []),
    [bundle],
  );

  const go = useCallback(
    (next: number) => {
      setIdx((prev) => {
        const v = clampStep(typeof next === "number" ? next : prev, steps.length);
        try {
          const u = new URL(window.location.href);
          u.searchParams.set("step", String(v));
          window.history.replaceState(null, "", u);
        } catch {
          /* file:// or sandboxed contexts */
        }
        return v;
      });
    },
    [steps.length],
  );

  // Browser back/forward moves through steps.
  useEffect(() => {
    const onPop = () => setIdx(parseStepParam(window.location.search, steps.length));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [steps.length]);

  // Every stepping action available by keyboard (WCAG 2.2 AA target).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, select, button, a, [contenteditable=true], [role=slider], .lecture-table, .lecture-code pre")) return;
      if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) e.preventDefault();
      if (e.key === "ArrowRight") go(idx + 1);
      else if (e.key === "ArrowLeft") go(idx - 1);
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(steps.length - 1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [go, idx, steps.length]);

  const nextStep = useRef(() => go(idx + 1));
  nextStep.current = () => go(idx + 1);

  // Keep the registered command pointed at current navigation state.
  useEffect(() => {
    if (!regs.commands.get("step.next")) {
      regs.commands.register({ id: "step.next", title: "Forward", keybinding: "ArrowRight", run: () => nextStep.current() });
    }
  }, [regs.commands]);

  if (error) {
    return (
      <main className="shell">
        <h1>lectpy shell</h1>
        <p role="alert">Could not load bundle: {error}</p>
        <p className="muted">
          Copy a trace with <code>npm run dev:sample</code> (uses
          <code>dist/lecture_01/lecture.json</code>) or pass{" "}
          <code>?bundle=/path/to/lecture.json</code>.
        </p>
      </main>
    );
  }
  if (!bundle) {
    return (
      <main className="shell">
        <h1>lectpy shell</h1>
        <p className="muted">Loading bundle…</p>
      </main>
    );
  }

  const s = steps[idx];
  const payload = (s?.payload ?? {}) as Record<string, unknown>;
  const locals = (payload["locals"] ?? {}) as Record<string, string>;
  const currentLine = typeof payload["line"] === "number" ? (payload["line"] as number) : null;
  const outputs = visibleOutputs(bundle.events, steps, idx);
  const inspects = visibleInspects(bundle.events, steps, idx);

  return (
    <main className="shell">
      <header className="top">
        <h1>{bundle.manifest.title}</h1>
        <span className="muted">
          shell · lectpy v0.3 · {bundle.manifest.policy_profile}
          {liveLabel ? ` · ${liveLabel}` : ""}
        </span>
      </header>
      {liveMode && liveInitial ? (
        <Suspense fallback={<p role="status">Loading live tools…</p>}>
          <LivePanel
            initial={liveInitial}
            onLiveBundle={(b, label) => {
              setBundle(b);
              setLiveLabel(label);
              setIdx(parseStepParam(window.location.search, stepEvents(b.events).length));
            }}
          />
        </Suspense>
      ) : null}
      <StepBar
        idx={idx}
        count={steps.length}
        onFirst={() => go(0)}
        onPrev={() => go(idx - 1)}
        onNext={() => go(idx + 1)}
        onOver={() => go(idx + 1)}
        onLast={() => go(steps.length - 1)}
      />
      <div className={bundle.source ? "layout" : "layout document-layout"}>
        <section id="stage" tabIndex={0} aria-label="Lecture stage">
          {s ? (
            <p className="muted">
              {(payload["func"] as string) ?? ""} @ line {String(payload["line"] ?? "?")}
            </p>
          ) : (
            <p className="muted">Recorded document</p>
          )}
          <EnvInspector locals={locals} />
          <OutputView outputs={outputs} registry={regs.renderers} />
          <InspectsList inspects={inspects} />
        </section>
        {bundle.source ? (
          <SourcePane
            source={bundle.source}
            currentLine={currentLine}
            onSeekLine={(line) => go(stepIndexForLine(steps, line))}
          />
        ) : null}
      </div>
      <p className="muted">
        Keyboard: ←/→ step, Home/End first/last. Step is deep-linked via{" "}
        <code>?step=N</code>. Reduced-motion respected.
      </p>
    </main>
  );
}
