/** Shell chrome: step bar, inspectors, virtualized source pane, output view. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { LectureEvent, LectureSource } from "./protocol";
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
        {count === 0 ? "0 / 0" : `${idx + 1} / ${count}`}
      </span>
      <span id="meta" className="muted" role="status" aria-live="polite">
        {count === 0 ? "No steps recorded" : `Step ${idx + 1} of ${count}`}
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

const ROW_H = 22;
const VIEWPORT_H = 330;

export function SourcePane({
  source,
  currentLine,
  onSeekLine,
}: {
  source: LectureSource;
  currentLine: number | null;
  onSeekLine: (line: number) => void;
}) {
  const lines = useMemo(() => source.text.split("\n"), [source.text]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const win = virtualWindow(lines.length, ROW_H, VIEWPORT_H, scrollTop, 8);

  const currentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    currentRef.current?.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [currentLine]);

  return (
    <section aria-label={`Source: ${source.file}`}>
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
              ref={current ? currentRef : undefined}
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
  registry,
}: {
  outputs: LectureEvent[];
  registry: RendererRegistry;
}) {
  return (
    <>
      {outputs.map((e) => {
        const contrib = registry.resolve(e.kind);
        if (!contrib) return null;
        const C = contrib.component;
        return <C key={`${e.seq}`} event={e} />;
      })}
    </>
  );
}

export { stepIndexForLine };
