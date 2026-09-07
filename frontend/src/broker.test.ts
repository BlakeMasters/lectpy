import { describe, expect, it } from "vitest";
import {
  authHeaders,
  decodePtyBytes,
  normalizeBase,
  parseServerFrame,
  ptyInputFrame,
  ptyKillFrame,
  ptyResizeFrame,
  streamUrl,
  toLiveBundle,
  wsBase,
} from "./broker";

const CFG = { baseUrl: "http://127.0.0.1:7888/", token: "tok" };

describe("broker client plumbing", () => {
  it("builds auth headers and normalizes the base URL", () => {
    expect(authHeaders(CFG)).toEqual({ Authorization: "Bearer tok" });
    expect(normalizeBase("http://h:1///")).toBe("http://h:1");
  });

  it("derives the WS base from REST + health port", () => {
    expect(wsBase("http://127.0.0.1:7888", 54321)).toBe("ws://127.0.0.1:54321");
    expect(wsBase("https://host:9", 1)).toBe("wss://host:1");
    expect(wsBase("http://127.0.0.1:7888", null)).toBe("ws://127.0.0.1:7888");
  });

  it("builds stream/attach URLs with the token", () => {
    const s = streamUrl(CFG, "ws://127.0.0.1:1", "sess_x", 7);
    expect(s).toBe("ws://127.0.0.1:1/v1/sessions/sess_x/stream?token=tok&after_seq=7");
  });

  it("wraps streamed events into a live bundle", () => {
    const b = toLiveBundle("live: x.py", []);
    expect(b.manifest.title).toBe("live: x.py");
    expect(b.events).toEqual([]);
  });
});

describe("PTY frame helpers", () => {
  it("round-trips input frames and parses server frames", () => {
    const f = JSON.parse(ptyInputFrame("ls\r")) as { type: string; data: string };
    expect(f.type).toBe("input");
    expect(typeof f.data).toBe("string");
    expect(JSON.parse(ptyResizeFrame(80, 24))).toEqual({ type: "resize", cols: 80, rows: 24 });
    expect(JSON.parse(ptyKillFrame())).toEqual({ type: "kill" });

    const out = parseServerFrame(JSON.stringify({ type: "output", data: "AAA=", replay: true }));
    expect(out).toEqual({ type: "output", data: "AAA=", replay: true });
    expect(parseServerFrame(JSON.stringify({ type: "exit", code: 0 }))).toEqual({
      type: "exit",
      code: 0,
    });
    expect(
      parseServerFrame(JSON.stringify({ type: "event", event: { kind: "step", seq: 3 } })),
    ).toEqual({ type: "event", event: { kind: "step", seq: 3 } });
    expect(parseServerFrame("not json")).toEqual({ type: "unknown" });
  });

  it("decodes split multibyte sequences incrementally", () => {
    // "héllo": h | 0xC3 0xA9 | llo — split inside the 2-byte é.
    const full = new TextEncoder().encode("héllo");
    const b64 = (u: Uint8Array) => {
      let bin = "";
      for (const b of u) bin += String.fromCharCode(b);
      return btoa(bin);
    };
    const dec = new TextDecoder("utf-8");
    const part1 = decodePtyBytes(b64(full.slice(0, 2)), dec);
    const part2 = decodePtyBytes(b64(full.slice(2)), dec) + dec.decode();
    expect(part1 + part2).toBe("héllo");
  });
});
