/** Shell chrome: step bar, inspectors, virtualized source pane, output view. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { LectureEvent, LectureSource, TraceReference } from "./protocol";
import { RendererRegistry } from "./registry";
import { stepIndexForLine, virtualWindow } from "./select";

export function StepBar({
  idx,
  count,
  onFirst,
  onPrev,
  onNext,
  onOver,
  onLast,
}: {
  idx: number;
  count: number;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onOver: () => void;
  onLast: () => void;
}) {
  const atStart = idx <= 0;
  const atEnd = idx >= count - 1;
  return (
    <div id="stepbar" role="toolbar" aria-label="Lecture stepping">
      <button onClick={onFirst} disabled={atStart} aria-label="First step">
        |◀ First
      </button>
      <button onClick={onPrev} disabled={atStart} aria-label="Previous step">
        ← Back
      </button>
      <button onClick={onNext} disabled={atEnd} aria-label="Next step">
        Forward →
      </button>
      <button onClick={onOver} disabled={atEnd} aria-label="Step over">
        Step over
      </button>
      <button onClick={onLast} disabled={atEnd} aria-label="Last step">
        Last ▶|
      </button>
      <span id="pos" aria-hidden="true">
        {count === 0 ? "Document" : `${idx + 1} / ${count}`}
      </span>
      <span id="meta" className="muted" role="status" aria-live="polite">
        {count === 0 ? "Recorded document" : `Step ${idx + 1} of ${count}`}
      </span>
    </div>
  );
}

export function EnvInspector({ locals }: { locals: Record<string, string> }) {
  const keys = Object.keys(locals);
  if (keys.length === 0) return null;
  return (
    <details open>
      <summary>
        Environment ({keys.length})
      </summary>
      <pre className="code">{keys.map((k) => `${k} = ${locals[k]}`).join("\n")}</pre>
    </details>
  );
}

export function InspectsList({ inspects }: { inspects: LectureEvent[] }) {
  if (inspects.length === 0) return null;
  return (
    <details>
      <summary>Inspected values</summary>
      <pre className="code">
        {inspects
          .map((e) => {
            const p = e.payload ?? {};
            return `${String(p["name"] ?? "?")} = ${String(p["summary"] ?? "")}`;
          })
          .join("\n")}
      </pre>
    </details>
  );
}

export function TraceLocation({
  currentFunc,
  currentLine,
  reference,
  onSeekReference,
}: {
  currentFunc: string | null;
  currentLine: number | null;
  reference: TraceReference | null;
  onSeekReference: (reference: TraceReference) => void;
}) {
  if (currentLine == null && !reference) return null;
  return (
    <div className="trace-location" aria-label="Current trace location">
      <span className="trace-location-current">
        {(currentFunc || "main")} · line {currentLine ?? "?"}
      </span>
      {reference ? (
        <button
          type="button"
          className="trace-reference"
          onClick={() => onSeekReference(reference)}
          title={`Jump to ${reference.file}:${reference.line}`}
        >
          ref → {reference.func || "caller"}:{reference.line}
        </button>
      ) : null}
    </div>
  );
}

const ROW_H = 22;
const VIEWPORT_H = 330;

export function SourcePane({
  source,
  currentLine,
  highlightColor,
  onSeekLine,
}: {
  source: LectureSource;
  currentLine: number | null;
  highlightColor: string;
  onSeekLine: (line: number) => void;
}) {
  const lines = useMemo(() => source.text.split("\n"), [source.text]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const win = virtualWindow(lines.length, ROW_H, VIEWPORT_H, scrollTop, 8);

  // Keep the current line rendered AND visible. Imperative scrollTop (not
  // scrollIntoView) so the target row need not exist in the DOM yet — the
  // scroll event then re-renders the window around it.
  useEffect(() => {
    if (currentLine == null) return;
    const el = scrollRef.current;
    if (!el) return;
    const top = (currentLine - 1) * ROW_H;
    if (top < el.scrollTop || top + ROW_H > el.scrollTop + VIEWPORT_H) {
      el.scrollTop = Math.max(0, top - VIEWPORT_H / 2);
    }
  }, [currentLine]);

  return (
    <section
      aria-label={`Source: ${source.file}`}
      style={{ "--trace-highlight": highlightColor } as CSSProperties}
    >
      <h2 className="pane-title">Source · {source.file}</h2>
      <div
        ref={scrollRef}
        className="srcview"
        style={{ height: VIEWPORT_H }}
        tabIndex={0}
        role="log"
        aria-label="Lecture source"
        onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
      >
        <div style={{ height: win.topPad }} />
        {lines.slice(win.start, win.end).map((text, i) => {
          const line = win.start + i + 1;
          const current = line === currentLine;
          return (
            <div
              key={line}
              className={current ? "srcline current" : "srcline"}
              role="button"
              tabIndex={0}
              title={`Seek to line ${line}`}
              aria-current={current ? "true" : undefined}
              onClick={() => onSeekLine(line)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSeekLine(line);
                }
              }}
            >
              <span className="lineno">{line}</span>
              <code>{text || " "}</code>
            </div>
          );
        })}
        <div style={{ height: win.bottomPad }} />
      </div>
    </section>
  );
}

export function OutputView({
  outputs,
  activeOutputSeqs,
  registry,
}: {
  outputs: LectureEvent[];
  activeOutputSeqs: ReadonlySet<number>;
  registry: RendererRegistry;
}) {
  return (
    <>
      {outputs.map((e) => {
        const contrib = registry.resolve(e.kind);
        if (!contrib) return null;
        const C = contrib.component;
        const current = activeOutputSeqs.has(e.seq);
        return (
          <article
            key={`${e.seq}`}
            className={current ? "lecture-output lecture-output-current" : "lecture-output"}
            data-output-seq={e.seq}
            aria-current={current ? "step" : undefined}
          >
            <C event={e} />
          </article>
        );
      })}
    </>
  );
}

export { stepIndexForLine };
