/** Broker client for live mode (?live=1).
 *
 *  Same logical API as the daemon's REST+WS surface. Auth is a bearer token
 *  (typed once, kept in sessionStorage, never logged). `?token=` URL prefill
 *  exists for loopback demos/screenshots only — tokens in URLs leak into
 *  history, so remote deployments must not use it.
 */
import type { LectureBundle, LectureEvent } from "./protocol";

export interface BrokerConfig {
  baseUrl: string; // e.g. http://127.0.0.1:7888
  token: string;
}

export function authHeaders(cfg: BrokerConfig): Record<string, string> {
  return { Authorization: `Bearer ${cfg.token}` };
}

export function normalizeBase(url: string): string {
  return url.replace(/\/+$/, "");
}

export async function brokerFetch(
  cfg: BrokerConfig,
  path: string,
  init: RequestInit = {},
): Promise<unknown> {
  const res = await fetch(`${normalizeBase(cfg.baseUrl)}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeaders(cfg), ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(typeof body["error"] === "string" ? body["error"] : `broker ${res.status}`);
  }
  return body;
}

export interface HealthInfo {
  ok: boolean;
  version: string;
  ws_port: number | null;
}

export async function fetchHealth(cfg: BrokerConfig): Promise<HealthInfo> {
  // Health is unauthenticated; capabilities need the token.
  const res = await fetch(`${normalizeBase(cfg.baseUrl)}/v1/health`);
  if (!res.ok) throw new Error(`broker health ${res.status}`);
  return (await res.json()) as HealthInfo;
}

export function wsBase(httpBase: string, wsPort: number | null): string {
  const u = new URL(normalizeBase(httpBase));
  const proto = u.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${u.hostname}:${wsPort ?? u.port}`;
}

export function streamUrl(cfg: BrokerConfig, ws: string, sessionId: string, afterSeq = -1): string {
  return `${ws}/v1/sessions/${sessionId}/stream?token=${encodeURIComponent(cfg.token)}&after_seq=${afterSeq}`;
}

export function ptyAttachUrl(cfg: BrokerConfig, ws: string, ptyId: string): string {
  return `${ws}/v1/ptys/${ptyId}/attach?token=${encodeURIComponent(cfg.token)}`;
}

export async function openSession(cfg: BrokerConfig, document = "", policy = "local-trusted"): Promise<string> {
  const body = (await brokerFetch(cfg, "/v1/sessions", {
    method: "POST",
    body: JSON.stringify({ document, environment: {}, policy_profile: policy }),
  })) as { session_id: string };
  return body.session_id;
}

export async function runTrace(
  cfg: BrokerConfig,
  sessionId: string,
  entry: string,
): Promise<{ events: LectureEvent[]; steps: number }> {
  return (await brokerFetch(cfg, `/v1/sessions/${sessionId}/trace`, {
    method: "POST",
    body: JSON.stringify({ entry }),
  })) as { events: LectureEvent[]; steps: number };
}

export async function openPty(
  cfg: BrokerConfig,
  sessionId: string,
  cols = 100,
  rows = 30,
): Promise<{ pty_id: string; backend: string }> {
  return (await brokerFetch(cfg, `/v1/sessions/${sessionId}/pty`, {
    method: "POST",
    body: JSON.stringify({ cols, rows }),
  })) as { pty_id: string; backend: string };
}

export async function closeSession(cfg: BrokerConfig, sessionId: string): Promise<void> {
  await brokerFetch(cfg, `/v1/sessions/${sessionId}`, { method: "DELETE" });
}

export function toLiveBundle(title: string, events: LectureEvent[]): LectureBundle {
  return {
    manifest: {
      format_version: 1,
      title,
      source_file: "",
      source_sha256: "",
      runtime: "trace",
      policy_profile: "local-trusted",
    },
    events,
  };
}

// -- PTY WS frame helpers (wire is bytes; base64 inside JSON) ---------------

export function ptyInputFrame(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return JSON.stringify({ type: "input", data: btoa(bin) });
}

export function ptyResizeFrame(cols: number, rows: number): string {
  return JSON.stringify({ type: "resize", cols, rows });
}

export function ptyKillFrame(): string {
  return JSON.stringify({ type: "kill" });
}

export type ServerFrame =
  | { type: "output"; data: string; replay?: boolean }
  | { type: "exit"; code: number | null }
  | { type: "event"; event: LectureEvent }
  | { type: "hello"; session_id: string }
  | { type: "unknown" };

export function parseServerFrame(raw: string): ServerFrame {
  let msg: Record<string, unknown>;
  try {
    msg = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return { type: "unknown" };
  }
  if (msg["type"] === "output" && typeof msg["data"] === "string") {
    return { type: "output", data: msg["data"], replay: msg["replay"] === true };
  }
  if (msg["type"] === "exit") {
    return { type: "exit", code: typeof msg["code"] === "number" ? msg["code"] : null };
  }
  if (msg["type"] === "event" && typeof msg["event"] === "object") {
    return { type: "event", event: msg["event"] as LectureEvent };
  }
  if (msg["type"] === "hello") {
    return { type: "hello", session_id: String(msg["session_id"] ?? "") };
  }
  return { type: "unknown" };
}

/** Incremental UTF-8 decode for PTY byte frames (partial sequences survive). */
export function decodePtyBytes(b64: string, decoder: TextDecoder): string {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return decoder.decode(bytes, { stream: true });
}
