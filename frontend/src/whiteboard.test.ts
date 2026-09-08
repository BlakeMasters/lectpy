import { describe, expect, it } from "vitest";
import {
  acceptsPointer,
  BoardModel,
  drawingSvg,
  hitTest,
  pointerSample,
  pointerTool,
  validateDrawing,
} from "../../src/lecture/static/whiteboard.js";
import type { DrawingItem } from "../../src/lecture/static/whiteboard.js";

const item = (id: string, tool = "pen"): DrawingItem => ({
  id,
  tool,
  color: "#1d4ed8",
  width: 4,
  points: [
    { x: 10, y: 20, p: 0.2 },
    { x: 100, y: 50, p: 0.9 },
  ],
});
describe("whiteboard model", () => {
  it("keeps committed geometry stable and bounds undo history", () => {
    const model = new BoardModel();
    model.add(item("first"));
    const first = model.items[0];
    for (let i = 0; i < 210; i++) model.add(item(`next-${i}`));
    expect(model.items[0]).toBe(first);
    expect(model.undoStack.length).toBe(200);
    for (let i = 0; i < 200; i++) model.undo();
    expect(model.items.length).toBe(11);
  });
  it("supports transactional erasing, undo, redo and reversible clear", () => {
    const model = new BoardModel();
    model.add(item("a"));
    model.add(item("b", "rectangle"));
    model.add(item("c", "ellipse"));
    model.remove(new Set(["a", "c"]));
    expect(model.items.map((i) => i.id)).toEqual(["b"]);
    model.undo();
    expect(model.items.map((i) => i.id)).toEqual(["a", "b", "c"]);
    model.redo();
    expect(model.items.map((i) => i.id)).toEqual(["b"]);
    model.clear();
    expect(model.items).toEqual([]);
    model.undo();
    expect(model.items[0].id).toBe("b");
    model.add(item("d"));
    expect(model.redoStack).toEqual([]);
  });
  it("round-trips independent JSON snapshots and rejects malformed imports", () => {
    const model = new BoardModel();
    model.add(item("a"));
    const snapshot = model.snapshot();
    snapshot.items[0].points[0].x = 400;
    expect(model.items[0].points[0].x).toBe(10);
    expect(
      new BoardModel(JSON.parse(JSON.stringify(model.snapshot()))).items,
    ).toEqual(model.items);
    expect(() =>
      validateDrawing({ ...model.snapshot(), width: 50000 }),
    ).toThrow();
    expect(() => model.add({ ...item("b"), width: NaN })).toThrow();
    expect(() => model.add(item("a"))).toThrow();
    expect(() =>
      model.add({
        ...item("x"),
        points: Array(10001).fill({ x: 0, y: 0, p: 0.5 }),
      }),
    ).toThrow();
  });
  it("exports every tool as vector geometry with escaped text and pressure widths", () => {
    const model = new BoardModel();
    for (const tool of [
      "pen",
      "highlighter",
      "line",
      "arrow",
      "rectangle",
      "ellipse",
    ])
      model.add(item(tool, tool));
    model.add({ ...item("text", "text"), text: "<script> & equation" });
    const svg = drawingSvg(model.snapshot());
    expect(svg).toContain("<ellipse");
    expect(svg).toContain("<rect");
    expect(svg).toContain('opacity="0.28"');
    expect(svg).toContain("&lt;script&gt; &amp;");
    expect(svg).not.toContain("<script>");
    expect(svg).toContain('stroke-width="4.3');
    expect((svg.match(/<path/g) ?? []).length).toBe(5);
  });
  it("hit-tests strokes and shape outlines without erasing empty interiors", () => {
    expect(hitTest(item("a"), { x: 50, y: 33 })).toBe(true);
    expect(hitTest(item("a"), { x: 600, y: 600 })).toBe(false);
    const rectangle = {
      ...item("r", "rectangle"),
      points: [
        { x: 0, y: 0, p: 0.5 },
        { x: 200, y: 200, p: 0.5 },
      ],
    };
    expect(hitTest(rectangle, { x: 100, y: 100 })).toBe(false);
    expect(hitTest(rectangle, { x: 2, y: 100 })).toBe(true);
  });
});
describe("pen input", () => {
  it("preserves normalized pen pressure and scales/clamps responsive coordinates", () => {
    const bounds = { left: 20, top: 10, width: 600, height: 300 };
    expect(
      pointerSample(
        { clientX: 320, clientY: 160, pointerType: "pen", pressure: 0.8 },
        bounds,
        1200,
        600,
      ),
    ).toEqual({ x: 600, y: 300, p: 0.8 });
    expect(
      pointerSample(
        { clientX: 9999, clientY: -20, pointerType: "mouse", pressure: 0 },
        bounds,
        1200,
        600,
      ),
    ).toEqual({ x: 1200, y: 0, p: 0.5 });
  });
  it("rejects palms/secondary pointers and recognizes the hardware eraser", () => {
    expect(
      acceptsPointer({ pointerId: 1, pointerType: "touch", button: 0 }, true),
    ).toBe(false);
    expect(
      acceptsPointer({ pointerId: 1, pointerType: "touch", button: 0 }, false),
    ).toBe(true);
    expect(
      acceptsPointer({ pointerId: 2, pointerType: "pen", button: 0 }, true, 1),
    ).toBe(false);
    expect(
      acceptsPointer({ pointerId: 1, pointerType: "mouse", button: 2 }, true),
    ).toBe(false);
    expect(
      pointerTool({ pointerType: "pen", button: 5, buttons: 32 }, "pen"),
    ).toBe("eraser");
    expect(
      pointerTool({ pointerType: "pen", button: 0, buttons: 1 }, "highlighter"),
    ).toBe("highlighter");
  });
});
