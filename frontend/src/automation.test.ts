import { describe, expect, it, vi } from "vitest";
import { activeControlBindings, AutomationClient, navigationCommands } from "../../src/lecture/static/automation.js";
import type { ControlSpec } from "../../src/lecture/static/automation.js";

const spec: ControlSpec = {id:"popup", binding_id:"section-1", target:"popup", actions:[], on_enter:"open", on_leave:"keep"};

describe("section browser controls", () => {
  it("does not replay actions on rewind or an unchanged selection", () => {
    expect(navigationCommands([], [spec], false)).toEqual([]);
    const client = new AutomationClient("execution");
    client.run = vi.fn(async () => {});
    client.navigate([], [spec], 0, 1);
    client.navigate([], [spec], 0, 1);
    client.navigate([spec], [spec], 1, 1);
    client.navigate([], [spec], 2, 1);
    expect(client.run).toHaveBeenCalledTimes(1);
  });
  it("keeps shared targets open, but applies an explicit close on exit", () => {
    const close = {...spec, on_leave:"close"};
    expect(navigationCommands([close], [{...spec, binding_id:"section-2"}], true)
      .filter(c => c.action === "$close")).toEqual([]);
    expect(navigationCommands([close], [], false)[0].action).toBe("$close");
  });
  it("resolves the displayed output scope, including nested controls", () => {
    const event = {payload:{component_type:"playwright-controls",props:spec}};
    expect(activeControlBindings([{payload:{control_ids:[spec.binding_id]}}], [event])).toEqual([spec]);
    expect(activeControlBindings([{payload:{}}], [event])).toEqual([]);
  });
  it("does not connect a stale or unrelated bundle to the runner", async () => {
    const calls: RequestInit[] = [];
    const request: typeof fetch = async (_input, init) => {
      calls.push(init ?? {});
      return new Response(JSON.stringify({execution_id:"other",controls:{}}));
    };
    const client = new AutomationClient("execution", "", request);
    await client.refresh();
    expect(client.available).toBe(false);
    await client.run(spec, "$open", 0);
    expect(calls.every(call => call.method !== "POST")).toBe(true);
  });
});
