import { describe, expect, it, vi } from "vitest";
import { activeStepKeyables, handleStepKey, keySpecMatches } from "../../src/lecture/static/step_keyables.js";

const keyEvent = (key: string, overrides = {}) => ({
  key, altKey: false, ctrlKey: false, shiftKey: false, metaKey: false,
  preventDefault: vi.fn(), ...overrides,
} as unknown as KeyboardEvent);

describe("step keyboard routing", () => {
  it("matches exact modifiers, aliases, shifted letters, and space", () => {
    expect(keySpecMatches(keyEvent("P", { shiftKey: true, ctrlKey: true }), "Control+Shift+p")).toBe(true);
    expect(keySpecMatches(keyEvent(" "), "Space")).toBe(true);
    expect(keySpecMatches(keyEvent("ArrowRight", { shiftKey: true }), "ArrowRight")).toBe(false);
    for (const spec of ["Typo+ArrowRight", "Ctrl+Control+ArrowRight", "__proto__+ArrowRight"]) {
      expect(keySpecMatches(keyEvent("ArrowRight"), spec)).toBe(false);
    }
  });

  it("ignores malformed metadata and lets explicit output bindings override the scope", () => {
    const card = {
      getAttribute: () => JSON.stringify([null, {}, { key: "ArrowDown", action: "playback.pause" }]),
      querySelector: () => null,
    };
    const root = { querySelectorAll: () => [card] } as unknown as ParentNode;
    const bindings = activeStepKeyables(root, {
      payload: { step_keyables: [{ key: "ArrowDown", action: "step.next" }, null] },
    });
    expect(bindings.map(b => b.action)).toEqual(["playback.pause", "step.next"]);
  });

  it("routes configured navigation and preserves unbound modifier chords and handled events", () => {
    const navigate = vi.fn();
    const options = {
      root: { querySelectorAll: () => [] } as unknown as ParentNode,
      step: { payload: { step_keyables: [{ key: "Shift+ArrowRight", action: "step.last" }] } },
      reader: false, index: 1, count: 5, navigate,
    };
    handleStepKey(keyEvent("ArrowRight", { shiftKey: true }), options);
    expect(navigate).toHaveBeenLastCalledWith(4);
    handleStepKey(keyEvent("ArrowRight"), options);
    expect(navigate).toHaveBeenLastCalledWith(2);
    handleStepKey(keyEvent("ArrowRight", { ctrlKey: true }), options);
    handleStepKey(keyEvent("ArrowRight", { defaultPrevented: true }), options);
    handleStepKey(keyEvent("ArrowRight", { isComposing: true }), options);
    expect(navigate).toHaveBeenCalledTimes(2);
  });
});
