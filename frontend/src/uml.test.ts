import { expect, it } from "vitest";
import { umlSvg } from "../../src/lecture/static/uml.js";

it("keeps UML readable in the viewer's light or dark color scheme", () => {
  for (const kind of ["class", "sequence"]) {
    const svg = umlSvg(kind, {
      classes: [{name: "Model"}], participants: ["Trainer", "Model"],
      messages: [{from: "Trainer", to: "Model", label: "gradient(w)"}],
    });
    expect(svg).toContain('fill="CanvasText"');
    expect(svg).toContain('stroke="CanvasText"');
    expect(svg).not.toContain("#334155");
  }
});
