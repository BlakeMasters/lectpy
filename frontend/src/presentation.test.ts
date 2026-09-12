import { describe, expect, it } from "vitest";
import { sectionPresentation } from "./presentation";

describe("section presentation metadata", () => {
  it("accepts the bounded section vocabulary", () => {
    const result = sectionPresentation({
      session_id: "s",
      execution_id: "e",
      seq: 1,
      kind: "text",
      payload: {
        presentation: {
          name: "Evidence",
          tone: "evidence",
          density: "compact",
          width: "wide",
          align: "center",
        },
      },
    });
    expect(result.name).toBe("Evidence");
    expect(result.className).toContain("section-tone-evidence");
    expect(result.className).toContain("section-density-compact");
  });

  it("falls back safely for untrusted or missing metadata", () => {
    const result = sectionPresentation({
      session_id: "s",
      execution_id: "e",
      seq: 1,
      kind: "text",
      payload: { presentation: { name: "<bad>", tone: "url(javascript:x)" } },
    });
    expect(result.tone).toBe("neutral");
    expect(result.density).toBe("comfortable");
    expect(result.name).toBe("<bad>");
  });

  it("shares per-output font, sizing and focus options with static export", () => {
    const result = sectionPresentation({payload: {presentation: {
      font: "reading", text_size: "large", highlight: "violet", focus: "none",
    }}});
    expect(result.className).toContain("section-font-reading");
    expect(result.className).toContain("section-text-size-large");
    expect(result.className).toContain("section-highlight-violet");
    expect(result.className).toContain("section-focus-none");
    const fallback = sectionPresentation({payload: {presentation: {
      font: [], highlight: "red background", focus: null,
    }}});
    expect(fallback.font).toBe("viewer");
    expect(fallback.highlight).toBe("viewer");
    expect(fallback.focus).toBe("wash");
  });
});
