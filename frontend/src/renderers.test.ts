import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { NoteBlock, TextBlock } from "./renderers";
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
