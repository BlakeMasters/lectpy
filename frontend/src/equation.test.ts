import { describe, expect, it } from "vitest";
import { texToMathML } from "../../src/lecture/static/equation.js";

describe("equation rendering", () => {
  it("uses math identifiers for Greek variables", () => {
    expect(texToMathML(String.raw`\theta + \eta`)).toContain("<mi>θ</mi>");
  });
  it("makes progress through incomplete notation and excessive nesting", () => {
    expect(texToMathML("}x + ^_y")).toContain("<mo>}</mo>");
    expect(texToMathML("{".repeat(2000) + "x" + "}".repeat(2000))).toContain("<mtext>");
    expect(texToMathML(String.raw`\sqrt`.repeat(2000))).toContain("<mtext>");
  });
});
