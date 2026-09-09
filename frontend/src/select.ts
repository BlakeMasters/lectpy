/** Pure presentation-selection logic for the lecture shell.
 *
 *  Mirrors the static viewer's rule so both clients agree:
 *  - outputs visible at step `idx` are non-step events with
 *    `seq <= endSeq`, where the final step owns the tail (`Infinity`)
 *    since trailing outputs/crash errors have no later step;
 *  - anything at or before the latest `clear` (within range) is dropped;
 *  - protocol/control events (session_*, snapshot, clear, inspect) never
 *    render as outputs; inspects feed the inspector instead.
 */
import type { EventKind, LectureEvent, TraceReference } from "./protocol";

export const RENDERABLE_KINDS: readonly EventKind[] = [
  "text", "note", "image", "video", "link", "plot", "terminal", "component", "error",
];

export function stepEvents(events: LectureEvent[]): LectureEvent[] {
  return events.filter((e) => e.kind === "step");
}

export function clampStep(idx: number, count: number): number {
  if (count <= 0) return 0;
  if (!Number.isFinite(idx)) return 0;
  return Math.min(Math.max(Math.floor(idx), 0), count - 1);
}

/** Parse `?step=N` (0-based, as written by the shell/static viewer). */
export function parseStepParam(search: string, count: number): number {
  const raw = new URLSearchParams(search).get("step");
  const n = raw === null ? 0 : Number.parseInt(raw, 10);
  return clampStep(Number.isNaN(n) ? 0 : n, count);
}

export function endSeqFor(steps: LectureEvent[], idx: number): number {
  if (steps.length === 0) return Number.POSITIVE_INFINITY;
  if (idx >= steps.length - 1) return Number.POSITIVE_INFINITY;
  return steps[idx].seq;
}

export function clearSeqBefore(events: LectureEvent[], endSeq: number): number {
  let clearSeq = -1;
  for (const e of events) {
    if (e.kind === "clear" && e.seq <= endSeq && e.seq > clearSeq) clearSeq = e.seq;
  }
  return clearSeq;
}

export function visibleOutputs(
  events: LectureEvent[],
  steps: LectureEvent[],
  idx: number,
): LectureEvent[] {
  if (idx < 0) return [];
  const endSeq = endSeqFor(steps, idx);
  const clearSeq = clearSeqBefore(events, endSeq);
  return events.filter(
    (e) =>
      RENDERABLE_KINDS.includes(e.kind) && e.seq <= endSeq && e.seq > clearSeq,
  );
}

/** Output events introduced by the selected step.
 *
 * Trace steps are entry points: an output emitted while a line executes is
 * visible on the following step. Comparing adjacent projections keeps that
 * debugger behavior while giving the presenter one concrete output to mark as
 * the current teaching moment.
 */
export function currentOutputSeqs(
  events: LectureEvent[],
  steps: LectureEvent[],
  idx: number,
): number[] {
  const visible = visibleOutputs(events, steps, idx);
  if (visible.length === 0) return [];
  const prior = idx > 0 ? visibleOutputs(events, steps, idx - 1) : [];
  const priorSeqs = new Set(prior.map((event) => event.seq));
  return visible.filter((event) => !priorSeqs.has(event.seq)).map((event) => event.seq);
}

/** Browser-window commands visible at a selected step. */
export function visibleBrowserWindowEvents(
  events: LectureEvent[],
  steps: LectureEvent[],
  idx: number,
): LectureEvent[] {
  return visibleOutputs(events, steps, idx).filter((event) => {
    const payload = event.payload ?? {};
    return event.kind === "component" && payload["component_type"] === "browser-window";
  });
}

export type BrowserWindowAction = "open" | "close";

/** Last recorded command for each reference window at a selected step. */
export function browserWindowStateAt(
  events: LectureEvent[],
  steps: LectureEvent[],
  idx: number,
): Map<string, BrowserWindowAction> {
  const state = new Map<string, BrowserWindowAction>();
  visibleBrowserWindowEvents(events, steps, idx).forEach((event) => {
    const value = event.payload?.["props"];
    const props = value && typeof value === "object"
      ? value as Record<string, unknown>
      : {};
    const candidate = props["window_id"];
    const id = typeof candidate === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(candidate)
      ? candidate
      : "reference";
    state.set(id, props["action"] === "close" ? "close" : "open");
  });
  return state;
}

export function visibleInspects(
  events: LectureEvent[],
  steps: LectureEvent[],
  idx: number,
  limit = 8,
): LectureEvent[] {
  if (idx < 0) return [];
  const endSeq = endSeqFor(steps, idx);
  const clearSeq = clearSeqBefore(events, endSeq);
  return events
    .filter((e) => e.kind === "inspect" && e.seq <= endSeq && e.seq > clearSeq)
    .slice(-limit);
}

/** Shell-side URL-scheme policy — mirrors `sanitize._safe_url`. */
const ALLOWED_SCHEMES = new Set(["http", "https"]);
const ALLOWED_IMG_SCHEMES = new Set(["http", "https", "data", "blob"]);

export function isSafeUrl(url: string, forImg = false): boolean {
  const u = url.trim();
  if (!u) return false;
  const lowered = u.toLowerCase();
  if (
    lowered.startsWith("javascript:") ||
    lowered.startsWith("vbscript:") ||
    lowered.startsWith("data:text/html")
  ) {
    return false;
  }
  if (u.startsWith("#")) return true;
  const m = /^([a-zA-Z][a-zA-Z0-9+.-]*):/.exec(u);
  if (!m) return true; // relative URL
  const scheme = m[1].toLowerCase();
  if (forImg) {
    if (scheme === "data") return lowered.startsWith("data:image/");
    return ALLOWED_IMG_SCHEMES.has(scheme);
  }
  return ALLOWED_SCHEMES.has(scheme);
}

/** Virtual-window math: which rows to materialize for a fixed-row-height list.
 *  The shell renders tens of thousands of source lines without holding them
 *  all in the DOM — the same rule the 100k-line perf smoke test asserts.
 */
export interface VirtualWindow {
  start: number;
  end: number; // exclusive
  topPad: number; // px above the window
  bottomPad: number; // px below the window
}

export function virtualWindow(
  total: number,
  itemHeight: number,
  viewportHeight: number,
  scrollTop: number,
  overscan = 5,
): VirtualWindow {
  if (total <= 0 || itemHeight <= 0 || viewportHeight <= 0) {
    return { start: 0, end: 0, topPad: 0, bottomPad: 0 };
  }
  const first = Math.floor(Math.max(0, scrollTop) / itemHeight);
  const visible = Math.ceil(viewportHeight / itemHeight);
  const start = Math.max(0, first - overscan);
  const end = Math.min(total, first + visible + overscan);
  return {
    start,
    end,
    topPad: start * itemHeight,
    bottomPad: (total - end) * itemHeight,
  };
}

/** Step index whose line best matches a source-line click (first step at or
 *  after the line; falls back to the nearest earlier step).
 */
export function stepIndexForLine(
  steps: LectureEvent[],
  line: number,
): number {
  for (let i = 0; i < steps.length; i++) {
    const ln = (steps[i].payload?.["line"] as number | undefined) ?? -1;
    if (ln >= line) return i;
  }
  for (let i = steps.length - 1; i >= 0; i--) {
    const ln = (steps[i].payload?.["line"] as number | undefined) ?? -1;
    if (ln <= line) return i;
  }
  return 0;
}

function sourceFileName(value: string): string {
  return value.replaceAll("\\", "/").split("/").pop() ?? value;
}

/** Read the optional caller reference emitted by the Python trace provider. */
export function traceReference(step: LectureEvent | undefined): TraceReference | null {
  const value = step?.payload?.["ref"];
  if (!value || typeof value !== "object") return null;
  const ref = value as Record<string, unknown>;
  if (typeof ref["file"] !== "string" || typeof ref["line"] !== "number") return null;
  return {
    file: ref["file"],
    line: ref["line"],
    ...(typeof ref["func"] === "string" ? { func: ref["func"] } : {}),
  };
}

/** Find the step at a caller reference, falling back to its source line. */
export function stepIndexForReference(
  steps: LectureEvent[],
  reference: TraceReference,
): number {
  const refFile = sourceFileName(reference.file);
  const exact = steps.findIndex((step) => {
    const p = step.payload ?? {};
    const file = typeof p["file"] === "string" ? p["file"] : "";
    const line = typeof p["line"] === "number" ? p["line"] : -1;
    const func = typeof p["func"] === "string" ? p["func"] : undefined;
    return line === reference.line && (!reference.func || func === reference.func)
      && (!file || file === reference.file || sourceFileName(file) === refFile);
  });
  return exact >= 0 ? exact : stepIndexForLine(steps, reference.line);
}
