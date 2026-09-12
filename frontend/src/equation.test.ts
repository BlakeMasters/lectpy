import { describe, expect, it } from "vitest";
import { texToMathML } from "../../src/lecture/static/equation.js";

describe("equation rendering", () => {
  it("groups numbers without treating decimal points as operators", () => {
    const math = texToMathML("123.45 + .25 = 123.70");
    expect(math).toContain("<mn>123.45</mn>");
    expect(math).toContain("<mn>.25</mn>");
    expect(math).not.toContain("<mo>.</mo>");
  });
  it("keeps unbraced scripts and fraction arguments to one TeX token", () => {
    expect(texToMathML("x^23")).toContain("<msup><mi>x</mi><mn>2</mn></msup><mn>3</mn>");
    expect(texToMathML(String.raw`\frac12`)).toContain("<mfrac><mn>1</mn><mn>2</mn></mfrac>");
    expect(texToMathML("x^{2.25}")).toContain("<mn>2.25</mn>");
  });
  it("treats escaped braces and invisible delimiters as delimiters", () => {
    expect(texToMathML(String.raw`\left\{x\right\}`)).toContain("<mo>{</mo><mi>x</mi><mo>}</mo>");
    expect(texToMathML(String.raw`\left.x\right|`)).not.toContain("<mo>.</mo>");
  });
  it("does not silently drop the last character of an incomplete text group", () => {
    expect(texToMathML(String.raw`\text{value`)).toContain("value</mtext>");
  });
  it("uses math identifiers for Greek variables", () => {
    expect(texToMathML(String.raw`\theta + \eta`)).toContain("<mi>θ</mi>");
  });
  it("makes progress through incomplete notation and excessive nesting", () => {
    expect(texToMathML("}x + ^_y")).toContain("<mo>}</mo>");
    expect(texToMathML("{".repeat(2000) + "x" + "}".repeat(2000))).toContain("<mtext>");
    expect(texToMathML(String.raw`\sqrt`.repeat(2000))).toContain("<mtext>");
  });
});
