/** Shell chrome: step bar, inspectors, virtualized source pane, output view. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import type { LectureEvent, LectureSource, TraceReference } from "./protocol";
import { sectionPresentation } from "./presentation";
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

function valueType(value: string): string {
  const trimmed = value.trim();
  if (trimmed === "True" || trimmed === "False") return "bool";
  if (trimmed === "None") return "NoneType";
  if (/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?j?$/i.test(trimmed)) return "number";
  if (/^(?:[rubfRUBF]{0,2})(['\"])/.test(trimmed)) return "str";
  if (trimmed.startsWith("[")) return "list";
  if (trimmed.startsWith("{")) return "dict";
  if (trimmed.startsWith("(")) return "tuple";
  if (trimmed.startsWith("<")) return "object";
  return "value";
}

function stringPayload(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

export function VariableInspector({
  locals,
  previousLocals,
  currentFile,
  currentFunc,
  currentLine,
  reference,
  inspects,
}: {
  locals: Record<string, string>;
  previousLocals: Record<string, string>;
  currentFile: string | null;
  currentFunc: string | null;
  currentLine: number | null;
  reference: TraceReference | null;
  inspects: LectureEvent[];
}) {
  const keys = Object.keys(locals);
  return (
    <aside id="variable-panel" aria-label="Workspace variables">
      <div className="workspace-heading">
        <div>
          <div className="workspace-kicker">Workspace</div>
          <h2>Variables</h2>
        </div>
        <span className="workspace-count" aria-label={`${keys.length} variables`}>
          {keys.length}
        </span>
      </div>
      <p className="workspace-location">
        <code>{currentFunc || "main"}</code>
        <span>·</span>
        <span>line {currentLine ?? "?"}</span>
        {currentFile ? <span className="muted">· {currentFile.split(/[\\/]/).pop()}</span> : null}
      </p>
      <ol className="call-stack" aria-label="Trace call stack">
        <li className="call-stack-current">
          <code>{currentFunc || "main"}</code>
          <span>current frame</span>
        </li>
        {reference ? (
          <li>
            <code>ref → {reference.func || "caller"}</code>
            <span>{reference.file.split(/[\\/]/).pop()}:{reference.line}</span>
          </li>
        ) : null}
      </ol>
      <div className="variable-table-wrap">
        <table className="variable-table">
          <caption className="sr-only">Current variables with values and inferred types</caption>
          <thead>
            <tr><th scope="col">Name</th><th scope="col">Value</th><th scope="col">Type</th></tr>
          </thead>
          <tbody>
            {keys.map((name) => {
              const changed = !Object.prototype.hasOwnProperty.call(previousLocals, name)
                || previousLocals[name] !== locals[name];
              return (
                <tr key={name} className={changed ? "variable-row variable-row-changed" : "variable-row"}>
                  <th scope="row" className="variable-name"><code>{name}</code></th>
                  <td className="variable-value" title={locals[name]}><code>{locals[name]}</code></td>
                  <td className="variable-type">
                    <code>{valueType(locals[name])}</code>
                    {changed ? <span className="variable-change" title="New or changed at this step">new</span> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {keys.length === 0 ? <p className="muted">No locals in this frame.</p> : null}
      {inspects.length > 0 ? (
        <details className="workspace-inspects" open>
          <summary>Inspected values ({inspects.length})</summary>
          <ul>
            {inspects.map((event) => {
              const p = event.payload ?? {};
              const name = stringPayload(p, "name") || "?";
              const summary = stringPayload(p, "summary");
              const type = stringPayload(p, "type");
              const shape = Array.isArray(p["shape"]) ? ` shape=${p["shape"].join("×")}` : "";
              return (
                <li key={event.seq}>
                  <code>{name}</code>
                  <span className="muted"> · {type}{shape}</span>
                  <div className="inspect-summary" title={summary}>{summary}</div>
                </li>
              );
            })}
          </ul>
        </details>
      ) : null}
    </aside>
  );
}

/** Compatibility wrapper for callers that only have a local snapshot. */
export function EnvInspector({ locals }: { locals: Record<string, string> }) {
  return (
    <VariableInspector
      locals={locals}
      previousLocals={{}}
      currentFile={null}
      currentFunc={null}
      currentLine={null}
      reference={null}
      inspects={[]}
    />
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
      {outputs.map((e, index) => {
        const contrib = registry.resolve(e.kind);
        if (!contrib) return null;
        const C = contrib.component;
        const current = activeOutputSeqs.has(e.seq);
        const section = sectionPresentation(e);
        const previousSection = sectionPresentation(outputs[index - 1]).name;
        const showSectionMarker = Boolean(section.name && section.name !== previousSection);
        return (
          <article
            key={`${e.seq}`}
            className={`lecture-output ${section.className}${current ? " lecture-output-current" : ""}`}
            data-output-seq={e.seq}
            data-section={section.name || undefined}
            aria-current={current ? "step" : undefined}
          >
            {showSectionMarker ? <div className="section-marker" aria-hidden="true">{section.name}</div> : null}
            <C event={e} />
          </article>
        );
      })}
    </>
  );
}

export { stepIndexForLine };
