/** Lazy local-runner controls shared by standalone and React viewers. */
const automationClients = new Map();

export function activeControlBindings(outputs, events) {
  const ids = outputs.at(-1)?.payload?.control_ids;
  if (!Array.isArray(ids)) return [];
  return events.filter(e => e.payload?.component_type === "playwright-controls"
    && ids.includes(e.payload.props?.binding_id)).map(e => e.payload.props);
}

export function navigationCommands(before, after, forward) {
  const nextTargets = new Set(after.map(s => s.id));
  const priorBindings = new Set(before.map(s => s.binding_id));
  return [
    ...before.filter(s => s.on_leave === "close" && !nextTargets.has(s.id))
      .map(s => ({spec: s, action: "$close"})),
    ...(forward ? after.filter(s => s.on_enter === "open" && !priorBindings.has(s.binding_id))
      .map(s => ({spec: s, action: "$open"})) : []),
  ];
}

export class AutomationClient {
  constructor(executionId, base = "", request = (...args) => fetch(...args)) {
    this.executionId = executionId;
    this.endpoint = `${base.replace(/\/$/, "")}/_lecture/automation`;
    this.request = request;
    this.listeners = new Set();
    this.seen = new Set();
    this.states = {};
    this.available = false;
    this.message = "Checking local runner…";
    this.token = "";
    this.timer = null;
    this.pending = null;
    this.navigationQueue = Promise.resolve();
  }
  notify() { for (const listener of this.listeners) listener(); }
  async refresh() {
    if (this.pending) return this.pending;
    this.pending = (async () => {
      try {
        const response = await this.request(this.endpoint, {signal: AbortSignal.timeout(5000)});
        if (!response.ok) throw new Error("No local runner. Serve this bundle with --scripts to enable controls.");
        const data = await response.json();
        if (data.execution_id !== this.executionId) throw new Error("Runner/bundle mismatch. Rebuild and reload both viewers.");
        this.states = data.controls;
        this.token = data.token;
        this.available = true;
        this.message = "Local runner connected";
      } catch (error) {
        this.available = false;
        this.message = error.message || "Local runner unavailable";
      } finally {
        this.pending = null;
        this.notify();
        clearTimeout(this.timer);
        if (this.listeners.size && this.available && Object.values(this.states).some(s => s.busy || s.state === "running"))
          this.timer = setTimeout(() => this.refresh(), 400);
      }
    })();
    return this.pending;
  }
  subscribe(listener) {
    this.listeners.add(listener);
    listener();
    this.refresh();
    return () => {
      this.listeners.delete(listener);
      if (!this.listeners.size) clearTimeout(this.timer);
    };
  }
  async run(spec, action, step) {
    if (!this.available) await this.refresh();
    if (!this.available) return;
    const requestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    try {
      this.states[spec.id] = {...this.states[spec.id], state: "running", busy: true, message: "Sending…"};
      this.notify();
      const response = await this.request(this.endpoint, {
        method: "POST", signal: AbortSignal.timeout(5000),
        headers: {"Content-Type": "application/json", Authorization: `Bearer ${this.token}`},
        body: JSON.stringify({id: spec.id, action, step, request_id: requestId}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Command failed");
      if (this.pending) await this.pending;
      await this.refresh();
    } catch (error) {
      // Never automatically retry a command whose execution may already have started.
      if (this.pending) await this.pending;
      await this.refresh();
      const state = this.states[spec.id] || {};
      this.states[spec.id] = {...state,
        state: this.available && state.state !== "idle" ? state.state : "error",
        message: `${error.message}. ${this.available ? state.message || "" : "Reconnect to check the runner before retrying."}`,
      };
      this.notify();
    }
  }
  navigate(before, after, from, to) {
    if (from === to) return this.navigationQueue;
    const commands = navigationCommands(before, after, to > from).filter(command => {
      if (command.action === "$open") {
        if (this.seen.has(command.spec.binding_id)) return false;
        this.seen.add(command.spec.binding_id);
      }
      return true;
    });
    // In particular, a slow initial connection/open must not arrive after its
    // section's close command when the presenter advances quickly.
    this.navigationQueue = this.navigationQueue.then(async () => {
      for (const command of commands) await this.run(command.spec, command.action, to);
    }).catch(() => {});
    return this.navigationQueue;
  }
}

export function automationClient(executionId) {
  if (!automationClients.has(executionId)) {
    let base = "";
    const configured = new URLSearchParams(location.search).get("automation");
    if (configured) {
      try {
        const url = new URL(configured);
        if (url.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname))
          base = url.origin;
      } catch { /* Invalid optional endpoint: fall back to the same-origin runner. */ }
    }
    automationClients.set(executionId, new AutomationClient(executionId, base));
  }
  return automationClients.get(executionId);
}

const AUTOMATION_STYLE = `.lp-automation{font:14px/1.4 system-ui,sans-serif;padding:.6rem 0;border-block:1px solid #8885}.lp-automation .automation-strip{display:flex;gap:.4rem;align-items:center;flex-wrap:wrap}.lp-automation button{font:inherit;color:CanvasText;background:Canvas;border:1px solid #888;padding:.3rem .5rem;border-radius:2px;cursor:pointer}.lp-automation button:disabled{opacity:.5;cursor:default}.lp-automation button:focus-visible{outline:3px solid #2563eb;outline-offset:2px}.lp-automation p{margin:.4rem 0}.lp-automation figure{margin:1rem 0}.lp-automation img{display:block;max-width:100%;height:auto;max-height:65vh}.lp-automation figcaption{font-size:.9em}.lp-automation .automation-target{opacity:.75}`;

export function mountAutomation(host, spec, client) {
  const root = document.createElement("section");
  root.className = "lp-automation";
  root.setAttribute("aria-label", `Browser controls: ${spec.id}`);
  const style = document.createElement("style");
  style.textContent = AUTOMATION_STYLE;
  const toolbar = document.createElement("div");
  toolbar.className = "automation-strip";
  const name = document.createElement("strong");
  name.textContent = spec.id;
  toolbar.append(name);
  const buttons = [];
  const entries = [{label: "Open / focus", script: "$open"}, ...(spec.actions || []),
    {label: "Capture", script: "$capture"}, {label: "Stop", script: "$stop"},
    {label: "Close", script: "$close"}];
  for (const action of entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.onclick = () => client.run(spec, action.script,
      Number(new URLSearchParams(location.search).get("step")) || 0);
    buttons.push([button, action.script]);
    toolbar.append(button);
  }
  const reconnect = document.createElement("button");
  reconnect.type = "button";
  reconnect.textContent = "Reconnect";
  reconnect.onclick = () => client.refresh();
  toolbar.append(reconnect);
  const target = document.createElement("p");
  target.className = "automation-target";
  target.textContent = spec.target === "lecture"
    ? "Target: managed lecture window (not an arbitrary browser tab)."
    : "Target: managed popup; keep presenting while it is open.";
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  const captures = document.createElement("div");
  root.append(style, toolbar, target, status, captures);
  host.append(root);
  let captureKey = "";
  const unsubscribe = client.subscribe(() => {
    const state = client.states[spec.id] || {};
    const busy = state.busy ?? state.state === "running";
    status.textContent = client.available
      ? busy && state.state !== "running" ? "Target is busy with another control; Stop cancels its action." : state.message || "Ready"
      : client.message;
    reconnect.hidden = client.available;
    for (const [button, action] of buttons)
      button.disabled = !client.available || (action === "$stop" ? !busy : action === "$close" ? false : busy);
    const images = state.captures || [];
    const nextKey = images.map(image => image.id).join(",");
    if (nextKey === captureKey) return;
    captureKey = nextKey;
    captures.replaceChildren();
    for (const image of images) {
      const figure = document.createElement("figure"), img = document.createElement("img");
      img.src = `${client.endpoint}/captures/${image.id}.png`;
      img.alt = image.caption;
      const caption = document.createElement("figcaption"), save = document.createElement("a");
      caption.textContent = `${image.caption} · `;
      save.href = img.src;
      save.download = `${spec.id}-${image.id}.png`;
      save.textContent = "Save PNG";
      caption.append(save);
      figure.append(img, caption);
      captures.append(figure);
    }
  });
  return () => { unsubscribe(); root.remove(); };
}
