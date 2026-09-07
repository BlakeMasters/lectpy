import { describe, expect, it } from "vitest";
import { CommandRegistry, ExecutionRegistry, RendererRegistry } from "./registry";

const stub = () => null;

describe("RendererRegistry", () => {
  it("resolves by kind and rejects duplicates like plugins.py", () => {
    const r = new RendererRegistry();
    r.register({ kinds: ["text", "note"], component: stub, trusted: true });
    expect(r.resolve("text")?.trusted).toBe(true);
    expect(r.resolve("plot")).toBeUndefined();
    expect(() => r.register({ kinds: ["text"], component: stub, trusted: true })).toThrow(
      /already registered for text/,
    );
    expect(r.kinds()).toEqual(["note", "text"]);
  });
});

describe("CommandRegistry", () => {
  it("registers discoverable, remappable commands", () => {
    const c = new CommandRegistry();
    c.register({ id: "step.next", title: "Forward", keybinding: "ArrowRight", run: () => {} });
    c.register({ id: "step.prev", title: "Back", run: () => {} });
    expect(c.all().map((x) => x.id)).toEqual(["step.next", "step.prev"]);
    expect(() => c.register({ id: "step.next", title: "dup", run: () => {} })).toThrow(
      /already registered/,
    );
  });
});

describe("ExecutionRegistry", () => {
  it("tracks provider ids for the v0.3 broker handoff", () => {
    const e = new ExecutionRegistry();
    e.register({ id: "trace", displayName: "Python trace" });
    e.register({ id: "jupyter", displayName: "Jupyter kernel" });
    expect(e.ids()).toEqual(["jupyter", "trace"]);
    expect(e.get("trace")?.displayName).toBe("Python trace");
    expect(() => e.register({ id: "trace", displayName: "dup" })).toThrow(
      /already registered/,
    );
  });
});
