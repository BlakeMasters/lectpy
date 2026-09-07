import { describe, expect, it } from "vitest";
import type { LectureEvent } from "./protocol";
import {
  clampStep,
  clearSeqBefore,
  endSeqFor,
  isSafeUrl,
  parseStepParam,
  stepEvents,
  stepIndexForLine,
  virtualWindow,
  visibleInspects,
  visibleOutputs,
} from "./select";

function ev(seq: number, kind: LectureEvent["kind"], payload: Record<string, unknown> = {}): LectureEvent {
  return { session_id: "s", execution_id: "e", seq, kind, payload, schema_version: 1 };
}

const GOLDEN: LectureEvent[] = [
  ev(0, "session_start"),
  ev(1, "step", { line: 10 }),
  ev(2, "text", { markdown: "# T" }),
  ev(3, "inspect", { name: "w", summary: "1.0" }),
  ev(4, "step", { line: 11 }),
  ev(5, "clear"),
  ev(6, "step", { line: 12 }),
  ev(7, "text", { markdown: "# U" }),
  ev(8, "inspect", { name: "w", summary: "0.8" }),
  ev(9, "terminal", { output: "$ python --version" }),
  ev(10, "step", { line: 13 }), // last step owns the tail
  ev(11, "note", { markdown: "tail note" }),
  ev(12, "session_end"),
];

describe("step plumbing", () => {
  it("collects steps and clamps indices", () => {
    expect(stepEvents(GOLDEN).map((e) => e.seq)).toEqual([1, 4, 6, 10]);
    expect(clampStep(-3, 4)).toBe(0);
    expect(clampStep(99, 4)).toBe(3);
    expect(clampStep(2, 4)).toBe(2);
    expect(clampStep(0, 0)).toBe(0);
  });

  it("parses ?step= like the static viewer", () => {
    expect(parseStepParam("?step=2", 4)).toBe(2);
    expect(parseStepParam("", 4)).toBe(0);
    expect(parseStepParam("?step=nope", 4)).toBe(0);
    expect(parseStepParam("?step=99", 4)).toBe(3);
  });

  it("final step owns the tail (Infinity end seq)", () => {
    const steps = stepEvents(GOLDEN);
    expect(endSeqFor(steps, 0)).toBe(1);
    expect(endSeqFor(steps, 3)).toBe(Number.POSITIVE_INFINITY);
    expect(endSeqFor([], 0)).toBe(-1);
  });
});

describe("visible outputs", () => {
  const steps = stepEvents(GOLDEN);

  it("shows outputs up to the current step only", () => {
    expect(visibleOutputs(GOLDEN, steps, 0).map((e) => e.seq)).toEqual([]);
    expect(visibleOutputs(GOLDEN, steps, 1).map((e) => e.seq)).toEqual([2]);
  });

  it("drops everything at or before a clear", () => {
    expect(clearSeqBefore(GOLDEN, 6)).toBe(5);
    // Step at seq 6 is line-12 *entry*: text@7 belongs to that line's own
    // execution, so it first appears at the next step (debugger semantics).
    expect(visibleOutputs(GOLDEN, steps, 2).map((e) => e.seq)).toEqual([]);
    expect(visibleInspects(GOLDEN, steps, 2).map((e) => e.payload?.["summary"])).toEqual([]);
  });

  it("final step includes the tail note and terminal output", () => {
    const seqs = visibleOutputs(GOLDEN, steps, 3).map((e) => e.seq);
    expect(seqs).toEqual([7, 9, 11]);
    const insp = visibleInspects(GOLDEN, steps, 3);
    expect(insp.map((e) => e.payload?.["summary"])).toEqual(["0.8"]);
  });

  it("never renders protocol/control events as outputs", () => {
    const kinds = visibleOutputs(GOLDEN, steps, 3).map((e) => e.kind);
    expect(kinds).not.toContain("session_start");
    expect(kinds).not.toContain("session_end");
    expect(kinds).not.toContain("clear");
    expect(kinds).not.toContain("inspect");
  });
});

describe("URL safety mirrors the backend sanitizer", () => {
  it("blocks script vectors", () => {
    expect(isSafeUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeUrl("JaVaScRiPt:alert(1)")).toBe(false);
    expect(isSafeUrl("data:text/html,<script>")).toBe(false);
    expect(isSafeUrl("vbscript:msgbox(1)")).toBe(false);
  });

  it("allows http/https, relative and fragment links", () => {
    expect(isSafeUrl("https://example.com/x")).toBe(true);
    expect(isSafeUrl("http://example.com")).toBe(true);
    expect(isSafeUrl("./assets/a.png")).toBe(true);
    expect(isSafeUrl("#section")).toBe(true);
  });

  it("restricts images to image-capable schemes", () => {
    expect(isSafeUrl("data:image/png;base64,AAA", true)).toBe(true);
    expect(isSafeUrl("data:text/html,X", true)).toBe(false);
    expect(isSafeUrl("blob:https://x/y", true)).toBe(true);
    expect(isSafeUrl("ftp://x/y", true)).toBe(false);
  });
});

describe("virtual window", () => {
  it("windows a 100k-line source without materializing it", () => {
    const w = virtualWindow(100_000, 20, 400, 10_000, 5);
    expect(w.start).toBe(495);
    expect(w.end).toBe(525);
    expect(w.topPad).toBe(495 * 20);
    expect(w.bottomPad).toBe((100_000 - 525) * 20);
    expect(w.end - w.start).toBeLessThan(100);
  });

  it("clamps at the top and bottom edges", () => {
    const top = virtualWindow(100, 20, 400, 0, 5);
    expect(top.start).toBe(0);
    const bottom = virtualWindow(100, 20, 400, 1_000_000, 5);
    expect(bottom.end).toBe(100);
    expect(bottom.bottomPad).toBe(0);
  });

  it("handles degenerate inputs", () => {
    expect(virtualWindow(0, 20, 400, 0)).toEqual({ start: 0, end: 0, topPad: 0, bottomPad: 0 });
  });
});

describe("source-line seeking", () => {
  const steps = stepEvents(GOLDEN); // lines 10, 11, 12, 13
  it("seeks to the first step at or after the clicked line", () => {
    expect(stepIndexForLine(steps, 10)).toBe(0);
    expect(stepIndexForLine(steps, 11)).toBe(1);
  });
  it("falls back to the nearest earlier step past the end", () => {
    expect(stepIndexForLine(steps, 99)).toBe(3);
  });
});
