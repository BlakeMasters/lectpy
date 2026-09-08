import { describe, expect, it } from "vitest";
import { displayIndex, resolveView } from "./views";
import { visibleOutputs } from "./select";
import type { LectureEvent } from "./protocol";

describe("presentation views", () => {
  it("uses the URL choice, then the author default, then an appropriate legacy default", () => {
    expect(resolveView("reader", "presenter", 3)).toBe("reader");
    expect(resolveView(undefined, "presenter", 3)).toBe("presenter");
    expect(resolveView("unknown", "invalid", 3)).toBe("inspector");
    expect(resolveView(null, undefined, 0)).toBe("reader");
  });

  it("reads the final page without changing the inspection cursor or reviving cleared output", () => {
    const kinds: LectureEvent["kind"][] = ["step", "text", "clear", "step", "text", "step"];
    const events: LectureEvent[] = kinds.map((kind, seq) => ({
      kind, seq, session_id: "s", execution_id: "e", payload: {},
    }));
    const steps = events.filter((e) => e.kind === "step");
    const cursor = 0;
    expect(visibleOutputs(events, steps, displayIndex("reader", cursor, steps.length))
      .map((e) => e.seq)).toEqual([4]);
    expect(displayIndex("inspector", cursor, steps.length)).toBe(0);
    expect(displayIndex("presenter", cursor, steps.length)).toBe(0);
    expect(displayIndex("reader", cursor, 0)).toBe(0);
  });
});
