/** Small browser-window controller shared by the React and static viewers. */
const BROWSER_ID = /^[A-Za-z0-9_-]{1,64}$/;
const ALLOWED_SCHEMES = new Set(["http:", "https:"]);

export function browserWindowSpec(value = {}) {
  const id = typeof value.window_id === "string" && BROWSER_ID.test(value.window_id)
    ? value.window_id : "reference";
  let url = "";
  try {
    const parsed = new URL(String(value.url || ""));
    if (ALLOWED_SCHEMES.has(parsed.protocol)) url = parsed.href;
  } catch { /* invalid bundle data is rendered as a blocked reference */ }
  const integer = (input, fallback, low, high) => {
    const n = Number.isInteger(input) ? input : fallback;
    return Math.max(low, Math.min(high, n));
  };
  const position = input => Number.isInteger(input)
    ? Math.max(-10000, Math.min(10000, input)) : undefined;
  return {
    id,
    url,
    title: typeof value.title === "string" && value.title ? value.title.slice(0, 200) : "Reference",
    width: integer(value.width, 1200, 320, 4096),
    height: integer(value.height, 800, 240, 2160),
    left: position(value.left),
    top: position(value.top),
    resizable: value.resizable !== false,
    focus: value.focus !== false,
  };
}

export function browserWindowFeatures(spec) {
  const parts = ["popup=yes", `width=${spec.width}`, `height=${spec.height}`,
    `resizable=${spec.resizable ? "yes" : "no"}`];
  if (spec.left !== undefined) parts.push(`left=${spec.left}`);
  if (spec.top !== undefined) parts.push(`top=${spec.top}`);
  return parts.join(",");
}

export function browserWindowName(id) {
  return `lectpy_${id}`;
}

export class BrowserWindowController {
  constructor(hostWindow = typeof window === "undefined" ? undefined : window) {
    this.hostWindow = hostWindow;
    this.windows = new Map();
  }

  get(id) {
    const handle = this.windows.get(id);
    if (handle?.closed) this.windows.delete(id);
    return this.windows.get(id);
  }

  open(value) {
    const spec = browserWindowSpec(value);
    if (!spec.url || !this.hostWindow?.open) {
      return { ok: false, blocked: false, message: "Reference URL is not a valid http(s) URL." };
    }
    const current = this.get(spec.id);
    if (current) {
      if (spec.focus) { try { current.focus(); } catch { /* cross-origin focus can be denied */ } }
      return { ok: true, blocked: false, reused: true, message: `${spec.title} is already open.` };
    }
    let handle;
    try {
      handle = this.hostWindow.open(spec.url, browserWindowName(spec.id), browserWindowFeatures(spec));
    } catch {
      handle = null;
    }
    if (!handle) {
      return { ok: false, blocked: true, message: "The browser blocked the reference window; use the link below." };
    }
    this.windows.set(spec.id, handle);
    if (spec.focus) { try { handle.focus(); } catch { /* best effort */ } }
    return { ok: true, blocked: false, reused: false, message: `${spec.title} opened.` };
  }

  close(id) {
    const handle = this.get(id);
    if (!handle) return { ok: false, message: "No reference window is open." };
    try { handle.close(); } catch { /* a closed cross-origin proxy is harmless */ }
    this.windows.delete(id);
    return { ok: true, message: "Reference window closed." };
  }

  closeAll() {
    for (const id of [...this.windows.keys()]) this.close(id);
  }
}
