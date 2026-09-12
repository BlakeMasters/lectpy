import { describe, expect, it, vi } from "vitest";
import { activeControlBindings, AutomationClient, navigationCommands } from "../../src/lecture/static/automation.js";
import type { ControlSpec } from "../../src/lecture/static/automation.js";

const spec: ControlSpec = {id:"popup", binding_id:"section-1", target:"popup", actions:[], on_enter:"open", on_leave:"keep"};

describe("section browser controls", () => {
  it("recovers the running job state after an ambiguous command response", async () => {
    let started = false;
    let posts = 0;
    const request: typeof fetch = async (_input, init) => {
      if (init?.method === "POST") {
        posts++; started = true;
        throw new Error("Connection lost after submission");
      }
      return new Response(JSON.stringify({execution_id:"execution", token:"test", controls:{
        popup:{state:started ? "running" : "idle", message:started ? "Running…" : "Ready"},
      }}));
    };
    const client = new AutomationClient("execution", "", request);
    await client.run(spec, "$open", 0);
    expect(posts).toBe(1);
    expect(client.states.popup.state).toBe("running");
  });
  it("does not replay actions on rewind or an unchanged selection", async () => {
    expect(navigationCommands([], [spec], false)).toEqual([]);
    const client = new AutomationClient("execution");
    client.run = vi.fn(async () => {});
    await client.navigate([], [spec], 0, 1);
    await client.navigate([], [spec], 0, 1);
    await client.navigate([spec], [spec], 1, 1);
    await client.navigate([], [spec], 2, 1);
    expect(client.run).toHaveBeenCalledTimes(1);
  });
  it("does not let a quick section exit overtake a delayed open request", async () => {
    const client = new AutomationClient("execution");
    let release!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    const sent: string[] = [];
    client.run = async (_spec, action) => {
      if (action === "$open") await pending;
      sent.push(action);
    };
    const close = {...spec, on_leave:"close"};
    client.navigate([], [close], 0, 1);
    const leaving = client.navigate([close], [], 1, 2);
    release();
    await leaving;
    expect(sent).toEqual(["$open", "$close"]);
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
