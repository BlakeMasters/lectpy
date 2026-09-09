import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EquationBlock, NoteBlock, TextBlock, UmlBlock } from "./renderers";
import type { LectureEvent } from "./protocol";

describe("text output compatibility", () => {
  it("shows legacy markdown-only results without interpreting markup as HTML", () => {
    const event: LectureEvent = {
      session_id: "s", execution_id: "e", seq: 0, kind: "text",
      payload: { markdown: "result: 2 < 3" },
    };
    for (const component of [TextBlock, NoteBlock]) {
      expect(renderToStaticMarkup(createElement(component, { event }))).toContain("2 &lt; 3");
    }
  });
});

describe("structured visual outputs", () => {
  it("renders equations as native MathML with an accessible label", () => {
    const event: LectureEvent = {
      session_id: "s", execution_id: "e", seq: 1, kind: "equation",
      payload: { tex: String.raw`\frac{a}{b}`, alt: "a divided by b", output_id: "fraction" },
    };
    const html = renderToStaticMarkup(createElement(EquationBlock, { event }));
    expect(html).toContain("lecture-equation");
    expect(html).toContain("data-output-id=\"fraction\"");
    expect(html).toContain("<math");
    expect(html).toContain("<mfrac>");
    expect(html).toContain("a divided by b");
  });

  it("renders structured UML as SVG without depending on Mermaid", () => {
    const event: LectureEvent = {
      session_id: "s", execution_id: "e", seq: 2, kind: "uml",
      payload: {
        uml_kind: "class",
        output_id: "model",
        alt: "Lecture emits an equation",
        spec: {
          classes: [{ name: "Lecture", methods: ["step()"] }, { name: "Equation" }],
          relations: [{ from: "Lecture", to: "Equation", label: "emits" }],
        },
      },
    };
    const html = renderToStaticMarkup(createElement(UmlBlock, { event }));
    expect(html).toContain("lecture-uml");
    expect(html).toContain("data-output-id=\"model\"");
    expect(html).toContain("<svg");
    expect(html).toContain("Lecture");
    expect(html).toContain("emits");
  });
});
