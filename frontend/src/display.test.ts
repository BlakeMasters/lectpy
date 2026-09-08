import { describe, expect, it } from "vitest";
import { displayPreset, DISPLAY_PRESETS, highlightColor, HIGHLIGHT_COLORS } from "./display";

describe("modular display tokens", () => {
  it("provides stable typography presets without remote font dependencies", () => {
    expect(DISPLAY_PRESETS.map((preset) => preset.id)).toEqual(["system", "technical", "reading"]);
    expect(displayPreset("technical").codeFont).toContain("monospace");
  });

  it("provides selectable current-line highlight colors", () => {
    expect(HIGHLIGHT_COLORS.map((color) => color.id)).toContain("amber");
    expect(highlightColor("violet")).toBe("#7c3aed");
  });
});
