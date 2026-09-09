/** lectpy browser shell v0.3.
 *
 *  Loads a v1 lecture bundle (static `lecture.json` today; broker event
 *  subscription in v0.3) and renders the debugger-like lecture view:
 *  step bar, workspace variable inspector, renderer-registry outputs, virtualized
 *  source pane. All stepping is keyboard reachable and URL deep-linked.
 */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  OutputView,
  SourcePane,
  StepBar,
  TraceLocation,
  VariableInspector,
  stepIndexForLine,
} from "./components";
import {
  DISPLAY_PRESETS,
  displayPreset,
  HIGHLIGHT_COLORS,
  highlightColor,
} from "./display";
import type { DisplayPresetId, HighlightColorId } from "./display";
import { readLiveParams } from "./liveParams";
import { ResourceProvider } from "./resources";
import { WhiteboardSession } from "./Whiteboard";
import { applyBrowserWindowEvent, referenceWindowController } from "./browserWindowRuntime";
import type { ResourceEnvironment } from "./resources";
import { displayIndex, parseView, resolveView } from "./views";
import type { LectureBundle, LectureEvent } from "./protocol";
import {
  ComponentBlock,
  ErrorBlock,
  EquationBlock,
  ImageBlock,
  LinkBlock,
  NoteBlock,
  PlotBlock,
  TerminalBlock,
  TextBlock,
  UmlBlock,
  VideoBlock,
} from "./renderers";
import { CommandRegistry, ExecutionRegistry, RendererRegistry } from "./registry";
import {
  clampStep,
  browserWindowStateAt,
  currentOutputSeqs,
  parseStepParam,
  stepEvents,
  stepIndexForReference,
  traceReference,
  visibleBrowserWindowEvents,
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
  renderers.register({ kinds: ["equation"], component: EquationBlock, ...opts });
  renderers.register({ kinds: ["uml"], component: UmlBlock, ...opts });
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
  const [resourceEnvironment, setResourceEnvironment] = useState<ResourceEnvironment>({});
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [requestedView, setRequestedView] = useState(
    () => parseView(new URLSearchParams(window.location.search).get("view")),
  );
  const [displayId, setDisplayId] = useState<DisplayPresetId>("system");
  const [highlightId, setHighlightId] = useState<HighlightColorId>("amber");
  const [showSource, setShowSource] = useState(false);
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
      .then(async (r) => {
        if (!r.ok) throw new Error(`bundle fetch failed: ${r.status}`);
        return { bundle: await r.json() as LectureBundle, baseUrl: r.url };
      })
      .then(({ bundle: b, baseUrl }) => {
        if (cancelled) return;
        setBundle(b);
        setResourceEnvironment({ baseUrl, resources: b.resources });
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
  const view = resolveView(requestedView, bundle?.manifest.view, steps.length);

  useEffect(() => {
    if (view === "reader") setShowSource(false);
  }, [view]);

  function changeView(value: string) {
    const next = parseView(value);
    if (!next) return;
    setRequestedView(next);
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState(null, "", url);
  }

  const syncReferenceWindows = useCallback(
    (from: number, to: number) => {
      if (!bundle || from === to || view === "reader") return;
      const target = visibleBrowserWindowEvents(bundle.events, steps, to);
      if (to < from) {
        // Backward navigation is a state reconciliation, not a replay. A
        // historical open must never launch a stale popup just because the
        // cursor landed on a step where its output is still visible.
        const targetState = browserWindowStateAt(bundle.events, steps, to);
        const priorState = browserWindowStateAt(bundle.events, steps, from);
        const ids = new Set([...priorState.keys(), ...targetState.keys()]);
        ids.forEach((id) => {
          if (targetState.get(id) !== "open") referenceWindowController.close(id);
        });
        return;
      }
      const prior = new Set(
        visibleBrowserWindowEvents(bundle.events, steps, from).map((event) => event.seq),
      );
      target.filter((event) => !prior.has(event.seq)).forEach((event) => {
        applyBrowserWindowEvent(event);
      });
    },
    [bundle, steps, view],
  );

  const go = useCallback(
    (next: number) => {
      const v = clampStep(typeof next === "number" ? next : idx, steps.length);
      syncReferenceWindows(idx, v);
      setIdx(v);
      try {
        const u = new URL(window.location.href);
        u.searchParams.set("step", String(v));
        window.history.replaceState(null, "", u);
      } catch {
        /* file:// or sandboxed contexts */
      }
    },
    [idx, steps.length, syncReferenceWindows],
  );

  // Browser back/forward moves through steps.
  useEffect(() => {
    const onPop = () => {
      const next = parseStepParam(window.location.search, steps.length);
      syncReferenceWindows(idx, next);
      setIdx(next);
      setRequestedView(parseView(new URLSearchParams(window.location.search).get("view")));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [idx, steps.length, syncReferenceWindows]);

  // Every stepping action available by keyboard (WCAG 2.2 AA target).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (view === "reader") return;
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
  }, [go, idx, steps.length, view]);

  // Keep the teaching output, rather than the source pane, in the presenter’s
  // reading position after a step transition.
  useEffect(() => {
    if (view !== "presenter" || !bundle) return;
    const frame = window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>("#stage .lecture-output-current")
        ?.scrollIntoView({ block: "center" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [bundle, idx, view]);

  const nextStep = useRef(() => go(idx + 1));
  nextStep.current = () => { if (view !== "reader") go(idx + 1); };

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
  const previousPayload = (idx > 0 ? steps[idx - 1]?.payload : undefined) as Record<string, unknown> | undefined;
  const previousLocals = previousPayload?.["func"] === payload["func"]
    ? (previousPayload?.["locals"] ?? {}) as Record<string, string>
    : {};
  const currentFile = typeof payload["file"] === "string" ? payload["file"] : null;
  const currentLine = typeof payload["line"] === "number" ? (payload["line"] as number) : null;
  const currentFunc = typeof payload["func"] === "string" ? (payload["func"] as string) : null;
  const reference = traceReference(s);
  const display = displayPreset(displayId);
  const currentHighlight = highlightColor(highlightId);
  const sourceVisible = Boolean(bundle.source && showSource && view !== "reader");
  const shownIdx = displayIndex(view, idx, steps.length);
  const outputs = visibleOutputs(bundle.events, steps, shownIdx);
  const activeOutputSeqs = new Set(currentOutputSeqs(bundle.events, steps, shownIdx));
  const inspects = visibleInspects(bundle.events, steps, shownIdx);
  const shellStyle = {
    "--lectpy-body-font": display.bodyFont,
    "--lectpy-code-font": display.codeFont,
    "--lectpy-font-scale": display.scale,
    "--lectpy-line-height": display.lineHeight,
    "--trace-highlight": currentHighlight,
  } as CSSProperties;

  return (
    <main className={`shell view-${view}`} style={shellStyle}>
      <header className="top">
        <h1>{bundle.manifest.title}</h1>
        <span className="muted">
          shell · lectpy v0.3 · {bundle.manifest.policy_profile}
          {liveLabel ? ` · ${liveLabel}` : ""}
        </span>
      </header>
      <div className="viewbar">
        <label>
          View{" "}
          <select value={view} onChange={(e) => changeView(e.target.value)}>
            <option value="reader">Reader</option>
            <option value="presenter">Presenter</option>
            <option value="inspector">Inspector</option>
          </select>
        </label>
        <label>
          Display{" "}
          <select
            value={displayId}
            onChange={(e) => setDisplayId(e.target.value as DisplayPresetId)}
          >
            {DISPLAY_PRESETS.map((preset) => (
              <option key={preset.id} value={preset.id}>{preset.label}</option>
            ))}
          </select>
        </label>
        <label>
          Output highlight{" "}
          <select
            value={highlightId}
            onChange={(e) => setHighlightId(e.target.value as HighlightColorId)}
          >
            {HIGHLIGHT_COLORS.map((color) => (
              <option key={color.id} value={color.id}>{color.label}</option>
            ))}
          </select>
        </label>
        {bundle.source ? (
          <button
            type="button"
            className="source-toggle"
            aria-pressed={showSource}
            disabled={view === "reader"}
            onClick={() => setShowSource((visible) => !visible)}
          >
            {sourceVisible ? "Hide source" : "Show source"}
          </button>
        ) : null}
        <span className="muted" role="status">
          {view === "reader" ? "Final recorded page" : view === "presenter" ? "Presentation with stepping" : "Source and state inspection"}
        </span>
      </div>
      {liveMode && liveInitial ? (
        <Suspense fallback={<p role="status">Loading live tools…</p>}>
          <LivePanel
            initial={liveInitial}
            onLiveBundle={(b, label, broker) => {
              setBundle(b);
              setResourceEnvironment({ broker });
              setLiveLabel(label);
              setIdx(parseStepParam(window.location.search, stepEvents(b.events).length));
            }}
          />
        </Suspense>
      ) : null}
      {view !== "reader" && <StepBar
        idx={idx}
        count={steps.length}
        onFirst={() => go(0)}
        onPrev={() => go(idx - 1)}
        onNext={() => go(idx + 1)}
        onOver={() => go(idx + 1)}
        onLast={() => go(steps.length - 1)}
      />}
      {view !== "reader" ? (
        <TraceLocation
          currentFunc={currentFunc}
          currentLine={currentLine}
          reference={reference}
          onSeekReference={(ref) => go(stepIndexForReference(steps, ref))}
        />
      ) : null}
      <div className={`${sourceVisible ? "layout trace-layout" : "layout document-layout"}${view === "inspector" ? " inspector-layout" : ""}`}>
        {sourceVisible ? (
          <SourcePane
            source={bundle.source!}
            currentLine={currentLine}
            highlightColor={currentHighlight}
            onSeekLine={(line) => go(stepIndexForLine(steps, line))}
          />
        ) : null}
        <section id="stage" tabIndex={0} aria-label="Lecture stage">
          <ResourceProvider environment={resourceEnvironment}>
            <WhiteboardSession key={bundle.events[0]?.execution_id ?? "empty"}>
              <OutputView
                outputs={outputs}
                activeOutputSeqs={activeOutputSeqs}
                registry={regs.renderers}
              />
            </WhiteboardSession>
          </ResourceProvider>
        </section>
        {view === "inspector" ? (
          <VariableInspector
            locals={locals}
            previousLocals={previousLocals}
            currentFile={currentFile}
            currentFunc={currentFunc}
            currentLine={currentLine}
            reference={reference}
            inspects={inspects}
          />
        ) : null}
      </div>
      {view === "inspector" && <p className="muted">
        Keyboard: ←/→ step, Home/End first/last. Step is deep-linked via{" "}
        <code>?step=N</code>. Reduced-motion respected.
      </p>}
    </main>
  );
}
