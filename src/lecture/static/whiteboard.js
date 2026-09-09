/** Dependency-free whiteboard. Shared verbatim by static export and React. */
export const TOOLS = [
  "pen",
  "highlighter",
  "eraser",
  "line",
  "arrow",
  "rectangle",
  "ellipse",
  "text",
];
const LIMITS = { items: 2000, points: 100000, stroke: 10000 };
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const finite = (n) => typeof n === "number" && Number.isFinite(n);
const escapeXml = (s) =>
  String(s).replace(
    /[<>&"']/g,
    (c) =>
      ({
        "<": "&lt;",
        ">": "&gt;",
        "&": "&amp;",
        '"': "&quot;",
        "'": "&apos;",
      })[c],
  );

export function pointerSample(event, rect, width, height) {
  return {
    x: clamp(((event.clientX - rect.left) * width) / rect.width, 0, width),
    y: clamp(((event.clientY - rect.top) * height) / rect.height, 0, height),
    p:
      event.pointerType === "pen" && finite(event.pressure)
        ? clamp(event.pressure, 0.05, 1)
        : 0.5,
  };
}
export function acceptsPointer(event, penOnly, activeId = null) {
  if (activeId !== null && event.pointerId !== activeId) return false;
  if (penOnly && event.pointerType === "touch") return false;
  return (
    event.button === 0 ||
    (event.pointerType === "pen" && (event.button === 5 || event.button === 2))
  );
}
export function pointerTool(event, tool) {
  return event.pointerType === "pen" &&
    (event.button === 5 || event.buttons & 32)
    ? "eraser"
    : tool;
}
const distance = (p, a, b) => {
  const dx = b.x - a.x,
    dy = b.y - a.y;
  const t = clamp(
    ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy || 1),
    0,
    1,
  );
  return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy);
};
export function hitTest(item, p, radius = 12) {
  const a = item.points[0],
    b = item.points.at(-1),
    pad = radius + item.width / 2;
  if (item.tool === "text")
    return (
      p.x >= a.x - pad &&
      p.x <= a.x + item.text.length * item.width * 0.65 + pad &&
      p.y >= a.y - item.width - pad &&
      p.y <= a.y + pad
    );
  if (["rectangle", "ellipse"].includes(item.tool)) {
    const left = Math.min(a.x, b.x),
      top = Math.min(a.y, b.y),
      w = Math.abs(a.x - b.x),
      h = Math.abs(a.y - b.y);
    if (item.tool === "ellipse") {
      const rx = w / 2 || 1,
        ry = h / 2 || 1;
      return (
        Math.abs(
          Math.hypot((p.x - left - rx) / rx, (p.y - top - ry) / ry) - 1,
        ) *
          Math.min(rx, ry) <=
        pad
      );
    }
    return (
      Math.min(
        distance(p, { x: left, y: top }, { x: left + w, y: top }),
        distance(p, { x: left + w, y: top }, { x: left + w, y: top + h }),
        distance(p, { x: left + w, y: top + h }, { x: left, y: top + h }),
        distance(p, { x: left, y: top + h }, { x: left, y: top }),
      ) <= pad
    );
  }
  return item.points.length === 1
    ? Math.hypot(p.x - a.x, p.y - a.y) <= pad
    : item.points
        .slice(1)
        .some((point, i) => distance(p, item.points[i], point) <= pad);
}

export function validateDrawing(value) {
  if (
    !value ||
    value.version !== 1 ||
    !finite(value.width) ||
    !finite(value.height) ||
    value.width < 320 ||
    value.width > 3840 ||
    value.height < 180 ||
    value.height > 2160 ||
    !["blank", "grid", "dots"].includes(value.background) ||
    !Array.isArray(value.items) ||
    value.items.length > LIMITS.items
  )
    throw new Error("Invalid whiteboard document");
  let total = 0;
  const ids = new Set();
  const items = value.items.map((item) => {
    if (
      !item ||
      typeof item.id !== "string" ||
      item.id.length > 100 ||
      ids.has(item.id) ||
      !TOOLS.includes(item.tool) ||
      item.tool === "eraser" ||
      !/^#[0-9a-f]{6}$/i.test(item.color) ||
      !finite(item.width) ||
      item.width < 1 ||
      item.width > 96 ||
      !Array.isArray(item.points) ||
      !item.points.length ||
      item.points.length > LIMITS.stroke ||
      (total += item.points.length) > LIMITS.points ||
      (item.tool === "text" &&
        (typeof item.text !== "string" || item.text.length > 1000))
    )
      throw new Error("Invalid or oversized whiteboard item");
    ids.add(item.id);
    return {
      id: item.id,
      tool: item.tool,
      color: item.color,
      width: item.width,
      ...(item.tool === "text" ? { text: item.text } : {}),
      points: item.points.map((p) => {
        if (
          !p ||
          !finite(p.x) ||
          !finite(p.y) ||
          !finite(p.p) ||
          p.x < 0 ||
          p.x > value.width ||
          p.y < 0 ||
          p.y > value.height ||
          p.p < 0 ||
          p.p > 1
        )
          throw new Error("Invalid stroke point");
        return { x: p.x, y: p.y, p: p.p };
      }),
    };
  });
  return {
    version: 1,
    width: value.width,
    height: value.height,
    background: value.background,
    items,
  };
}

export class BoardModel {
  constructor(
    drawing = {
      version: 1,
      width: 1200,
      height: 675,
      background: "grid",
      items: [],
    },
  ) {
    this.drawing = validateDrawing(drawing);
    this.undoStack = [];
    this.redoStack = [];
  }
  get items() {
    return this.drawing.items;
  }
  command(removed, added) {
    if (!removed.length && !added.length) return;
    const command = { removed, added };
    this.apply(command);
    this.undoStack.push(command);
    this.redoStack = [];
    // Bound retained geometry as well as command count (e.g. repeated imports).
    const cost = (entry) =>
      [...entry.added, ...entry.removed].reduce(
        (sum, value) =>
          sum +
          value.item.points.length +
          Math.ceil((value.item.text?.length || 0) / 16),
        0,
      );
    let retained = this.undoStack.reduce((sum, entry) => sum + cost(entry), 0);
    while (
      this.undoStack.length > 1 &&
      (this.undoStack.length > 200 || retained > 200000)
    ) {
      retained -= cost(this.undoStack.shift());
    }
  }
  apply(command, reverse = false) {
    const remove = reverse ? command.added : command.removed;
    const add = reverse ? command.removed : command.added;
    const ids = new Set(remove.map((entry) => entry.item.id));
    this.drawing.items = this.items.filter((item) => !ids.has(item.id));
    for (const entry of [...add].sort((a, b) => a.index - b.index))
      this.items.splice(entry.index, 0, entry.item);
  }
  add(item) {
    if (
      this.items.length >= LIMITS.items ||
      this.items.some((value) => value.id === item.id) ||
      this.items.reduce((sum, value) => sum + value.points.length, 0) +
        (item.points?.length || 0) >
        LIMITS.points
    )
      throw new Error("Duplicate item or whiteboard capacity reached");
    const next = validateDrawing({
      ...this.drawing,
      items: [item],
    });
    this.command([], [{ index: this.items.length, item: next.items[0] }]);
  }
  remove(ids) {
    this.command(
      this.items
        .map((item, index) => ({ item, index }))
        .filter((e) => ids.has(e.item.id)),
      [],
    );
  }
  clear() {
    this.remove(new Set(this.items.map((item) => item.id)));
  }
  undo() {
    const command = this.undoStack.pop();
    if (command) {
      this.apply(command, true);
      this.redoStack.push(command);
    }
  }
  redo() {
    const command = this.redoStack.pop();
    if (command) {
      this.apply(command);
      this.undoStack.push(command);
    }
  }
  snapshot() {
    return JSON.parse(JSON.stringify(this.drawing));
  }
}

function drawItem(ctx, item) {
  const a = item.points[0],
    b = item.points.at(-1);
  ctx.save();
  ctx.strokeStyle = item.color;
  ctx.fillStyle = item.color;
  ctx.lineWidth = item.width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  if (item.tool === "text") {
    ctx.font = `${item.width}px system-ui, sans-serif`;
    ctx.fillText(item.text, a.x, a.y);
  } else if (item.tool === "pen") {
    if (item.points.length === 1) {
      ctx.beginPath();
      ctx.arc(a.x, a.y, (item.width * (0.25 + 1.5 * a.p)) / 2, 0, Math.PI * 2);
      ctx.fill();
    }
    for (let i = 1; i < item.points.length; i++) {
      const p = item.points[i - 1],
        q = item.points[i];
      ctx.lineWidth = item.width * (0.25 + 0.75 * (p.p + q.p));
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(q.x, q.y);
      ctx.stroke();
    }
  } else {
    ctx.beginPath();
    if (item.tool === "rectangle")
      ctx.rect(
        Math.min(a.x, b.x),
        Math.min(a.y, b.y),
        Math.abs(b.x - a.x),
        Math.abs(b.y - a.y),
      );
    else if (item.tool === "ellipse")
      ctx.ellipse(
        (a.x + b.x) / 2,
        (a.y + b.y) / 2,
        Math.abs(b.x - a.x) / 2,
        Math.abs(b.y - a.y) / 2,
        0,
        0,
        Math.PI * 2,
      );
    else {
      ctx.moveTo(a.x, a.y);
      for (const p of item.points.slice(1)) ctx.lineTo(p.x, p.y);
      if (item.tool === "arrow") {
        const angle = Math.atan2(b.y - a.y, b.x - a.x),
          length = Math.max(12, item.width * 3);
        ctx.moveTo(
          b.x - length * Math.cos(angle - 0.5),
          b.y - length * Math.sin(angle - 0.5),
        );
        ctx.lineTo(b.x, b.y);
        ctx.lineTo(
          b.x - length * Math.cos(angle + 0.5),
          b.y - length * Math.sin(angle + 0.5),
        );
      }
    }
    if (item.tool === "highlighter") ctx.globalAlpha = 0.28;
    ctx.stroke();
  }
  ctx.restore();
}
function background(ctx, drawing) {
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, drawing.width, drawing.height);
  ctx.strokeStyle = "#e2e8f0";
  ctx.fillStyle = "#cbd5e1";
  ctx.lineWidth = 1;
  if (drawing.background === "grid") {
    ctx.beginPath();
    for (let x = 24; x < drawing.width; x += 24) {
      ctx.moveTo(x, 0);
      ctx.lineTo(x, drawing.height);
    }
    for (let y = 24; y < drawing.height; y += 24) {
      ctx.moveTo(0, y);
      ctx.lineTo(drawing.width, y);
    }
    ctx.stroke();
  } else if (drawing.background === "dots") {
    for (let x = 24; x < drawing.width; x += 24)
      for (let y = 24; y < drawing.height; y += 24) {
        ctx.beginPath();
        ctx.arc(x, y, 1, 0, Math.PI * 2);
        ctx.fill();
      }
  }
}
export function drawingSvg(drawing) {
  const d = validateDrawing(drawing);
  let content = '<rect width="100%" height="100%" fill="white"/>';
  if (d.background !== "blank")
    content += `<defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">${d.background === "grid" ? '<path d="M 24 0 L 0 0 0 24" fill="none" stroke="#e2e8f0"/>' : '<circle cx="0" cy="0" r="1" fill="#cbd5e1"/>'}</pattern></defs><rect width="100%" height="100%" fill="url(#grid)"/>`;
  for (const item of d.items) {
    const a = item.points[0],
      b = item.points.at(-1),
      style = `fill="none" stroke="${item.color}" stroke-width="${item.width}" stroke-linecap="round" stroke-linejoin="round"`;
    if (item.tool === "text")
      content += `<text x="${a.x}" y="${a.y}" fill="${item.color}" font-size="${item.width}" font-family="system-ui, sans-serif">${escapeXml(item.text)}</text>`;
    else if (item.tool === "rectangle")
      content += `<rect x="${Math.min(a.x, b.x)}" y="${Math.min(a.y, b.y)}" width="${Math.abs(b.x - a.x)}" height="${Math.abs(b.y - a.y)}" ${style}/>`;
    else if (item.tool === "ellipse")
      content += `<ellipse cx="${(a.x + b.x) / 2}" cy="${(a.y + b.y) / 2}" rx="${Math.abs(b.x - a.x) / 2}" ry="${Math.abs(b.y - a.y) / 2}" ${style}/>`;
    else if (item.tool === "pen") {
      if (item.points.length === 1)
        content += `<circle cx="${a.x}" cy="${a.y}" r="${(item.width * (0.25 + 1.5 * a.p)) / 2}" fill="${item.color}"/>`;
      for (let i = 1; i < item.points.length; i++) {
        const p = item.points[i - 1],
          q = item.points[i];
        content += `<path d="M${p.x} ${p.y}L${q.x} ${q.y}" fill="none" stroke="${item.color}" stroke-linecap="round" stroke-width="${item.width * (0.25 + 0.75 * (p.p + q.p))}"/>`;
      }
    } else {
      let path = item.points
        .map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`)
        .join("");
      if (item.tool === "arrow") {
        const t = Math.atan2(b.y - a.y, b.x - a.x),
          l = Math.max(12, item.width * 3);
        path += `M${b.x - l * Math.cos(t - 0.5)} ${b.y - l * Math.sin(t - 0.5)}L${b.x} ${b.y}L${b.x - l * Math.cos(t + 0.5)} ${b.y - l * Math.sin(t + 0.5)}`;
      }
      content += `<path d="${path}" ${style}${item.tool === "highlighter" ? ' opacity="0.28"' : ""}/>`;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${d.width}" height="${d.height}" viewBox="0 0 ${d.width} ${d.height}">${content}</svg>`;
}

const STYLE = `.lp-board{font:14px/1.4 system-ui,sans-serif;color:CanvasText;margin:1rem 0}.lp-board [hidden]{display:none!important}.lp-board button,.lp-board input,.lp-board select{font:inherit;color:CanvasText;background:Canvas;border:1px solid #888;border-radius:5px;padding:.4rem}.lp-board button{cursor:pointer}.lp-board button:disabled{opacity:.45}.lp-board :focus-visible{outline:3px solid #2563eb;outline-offset:2px}.lp-board .wb-toolbar{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:.5rem 0}.lp-board label{display:inline-flex;align-items:center;gap:.3rem}.lp-board input[type=text]{min-width:5rem;width:12rem;max-width:100%}.lp-board input[type=color]{width:2.5rem;height:2.3rem;padding:.15rem}.lp-board input[type=range]{width:6rem}.lp-board .wb-surface{position:relative;width:100%;background:white;border:1px solid #94a3b8;border-radius:5px;overflow:hidden}.lp-board canvas{position:absolute;inset:0;width:100%;height:100%;display:block}.lp-board canvas.wb-input{touch-action:none;cursor:crosshair}.lp-board .wb-help{font-size:.9em;opacity:.75;margin:.4rem 0}.lp-board .wb-commits{margin:1rem 0}.lp-board .wb-commit{border-block:1px solid #94a3b8;padding:.7rem 0;margin:.7rem 0}.lp-board .wb-commit-svg{max-width:100%;overflow:auto}.lp-board .wb-commit-svg svg{display:block;width:100%;height:auto}.lp-board .wb-commit-meta{font-size:.85em;opacity:.72}.lp-board:fullscreen{background:Canvas;padding:1rem;box-sizing:border-box;overflow:auto}.lp-board:fullscreen .wb-surface{max-height:75vh;width:auto;max-width:100%;margin:auto}`;

/** Mount into an owned node; state is caller-owned and survives replay remounts. */
export function mountWhiteboard(host, props = {}, state = {}) {
  const model =
    state.model ||
    new BoardModel(
      props.drawing || {
        version: 1,
        width: props.width || 1200,
        height: props.height || 675,
        background: props.background || "grid",
        items: [],
      },
    );
  state.model = model;
  const root = document.createElement("section");
  root.className = "lp-board";
  root.setAttribute("aria-label", props.title || "Whiteboard");
  root.innerHTML = `<style>${STYLE}</style><button class="wb-spawn" type="button"></button><div class="wb-panel" hidden>
    <div class="wb-toolbar"><strong class="wb-title"></strong><button type="button" data-action="close">Close whiteboard</button><button type="button" data-action="fullscreen">Full screen</button></div>
    <div class="wb-toolbar" role="group" aria-label="Drawing tools">
    <label>Tool <select class="wb-tool">${TOOLS.map((t) => `<option value="${t}">${t === "eraser" ? "Stroke eraser" : t[0].toUpperCase() + t.slice(1)}</option>`).join("")}</select></label>
    <label>Color <input class="wb-color" type="color" value="#1d4ed8"></label>
    <label>Size <input class="wb-size" type="range" min="1" max="48" value="4"><output class="wb-size-label">4</output></label>
    <label><input class="wb-pen-only" type="checkbox" checked> Ignore touch (pen + mouse)</label>
    <label>Paper <select class="wb-paper"><option value="blank">Blank</option><option value="grid">Grid</option><option value="dots">Dots</option></select></label>
    <button type="button" data-action="undo">Undo</button><button type="button" data-action="redo">Redo</button><button type="button" data-action="clear">Clear board</button></div>
    <div class="wb-toolbar"><label>Text <input class="wb-text" type="text" maxlength="1000" placeholder="Label or equation"></label><button type="button" data-action="text">Add text at center</button><button type="button" data-action="insert"${props.insertable === true ? "" : " hidden"}>Insert snapshot</button>
    <button type="button" data-action="svg">Save SVG</button><button type="button" data-action="png">Save PNG</button><button type="button" data-action="json">Save drawing</button>
    <label>Load drawing <input class="wb-file" type="file" accept="application/json,.json" style="max-width:13rem"></label></div>
    <div class="wb-surface"><canvas class="wb-base" aria-hidden="true"></canvas><canvas class="wb-input" tabindex="0" role="img" aria-label="Drawing surface. Use pen, mouse, or enabled touch. Use Add text at center for keyboard text input."></canvas></div>
    <p class="wb-help">Pair your stylus in your operating system. Pressure and eraser work when exposed by your device. Touch is ignored by default. Ctrl/Cmd+Z undoes; Shift+Z redoes. Drawings persist while stepping, not after reload; save to keep them.</p>
    <p class="wb-status" role="status" aria-live="polite"></p><p class="wb-download" hidden><a></a></p><details><summary>Board text alternative</summary><ul class="wb-description"></ul></details></div><div class="wb-commits" aria-live="polite"></div>`;
  host.append(root);
  const $ = (selector) => root.querySelector(selector);
  $(".wb-title").textContent = props.title || "Whiteboard";
  $(".wb-spawn").textContent = `Open ${props.title || "whiteboard"}`;
  const input = $(".wb-input"),
    base = $(".wb-base"),
    ctx = base.getContext("2d"),
    ink = input.getContext("2d");
  if (!ctx || !ink) {
    root.textContent = "Canvas is unavailable in this browser.";
    return () => root.remove();
  }
  const d = model.drawing;
  // Logical coordinates are stable across viewport changes; cap pixel memory.
  const ratio = Math.min(
    2,
    window.devicePixelRatio || 1,
    Math.sqrt(8000000 / (d.width * d.height)),
  );
  for (const canvas of [base, input]) {
    canvas.width = Math.round(d.width * ratio);
    canvas.height = Math.round(d.height * ratio);
  }
  for (const context of [ctx, ink]) context.scale(ratio, ratio);
  $(".wb-surface").style.aspectRatio = `${d.width}/${d.height}`;
  $(".wb-paper").value = d.background;
  const settings = state.settings || {};
  for (const name of ["tool", "color", "size", "text"])
    if (settings[name] !== undefined) $(".wb-" + name).value = settings[name];
  if (settings.penOnly !== undefined)
    $(".wb-pen-only").checked = settings.penOnly;
  $(".wb-size-label").value = $(".wb-size").value;
  let active = null,
    draft = null,
    eraseIds = new Set(),
    frame = 0,
    painted = 0,
    disposed = false;
  state.commits = Array.isArray(state.commits) ? state.commits : [];
  const status = (message) => {
    $(".wb-status").textContent = message;
  };
  const clearInk = () => ink.clearRect(0, 0, d.width, d.height);
  function renderCommits() {
    const commits = $(".wb-commits");
    commits.replaceChildren();
    if (!state.commits.length) return;
    const heading = document.createElement("h3");
    heading.textContent = "Inserted snapshots";
    commits.append(heading);
    for (const commit of state.commits) {
      const figure = document.createElement("figure");
      figure.className = "wb-commit";
      const visual = document.createElement("div");
      visual.className = "wb-commit-svg";
      visual.setAttribute("role", "img");
      visual.setAttribute("aria-label", commit.alt || "Inserted whiteboard snapshot");
      visual.innerHTML = commit.svg;
      const caption = document.createElement("figcaption");
      caption.className = "wb-commit-meta";
      caption.textContent = `Snapshot ${commit.revision}${commit.outputId ? ` · ${commit.outputId}` : ""}`;
      const description = document.createElement("p");
      description.textContent = commit.alt || "Inserted whiteboard snapshot";
      figure.append(visual, caption, description);
      commits.append(figure);
    }
  }
  function refresh(message) {
    background(ctx, d);
    for (const item of model.items)
      if (!eraseIds.has(item.id)) drawItem(ctx, item);
    $("[data-action=undo]").disabled = !model.undoStack.length;
    $("[data-action=redo]").disabled = !model.redoStack.length;
    const description = $(".wb-description");
    description.replaceChildren();
    for (const item of model.items.slice(-100)) {
      const li = document.createElement("li");
      li.textContent =
        item.tool === "text"
          ? item.text
          : `${item.tool}, ${item.color}, ${item.points.length} point(s)`;
      description.append(li);
    }
    renderCommits();
    status(
      message ||
        `${model.items.length} object(s). ${model.items.length > 100 ? "Last 100 described below." : ""}`,
    );
  }
  function redrawDraft() {
    frame = 0;
    if (!draft) return;
    if (draft.tool === "pen") {
      drawItem(ink, {
        ...draft,
        points: draft.points.slice(Math.max(0, painted - 1)),
      });
      painted = draft.points.length;
    } else {
      clearInk();
      drawItem(ink, draft);
    }
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(redrawDraft);
  }
  const point = (e) =>
    pointerSample(e, input.getBoundingClientRect(), d.width, d.height);
  const id = () =>
    globalThis.crypto?.randomUUID?.() || `item-${Date.now()}-${Math.random()}`;
  function makeItem(tool, p) {
    return {
      id: id(),
      tool,
      color: $(".wb-color").value,
      width:
        tool === "text"
          ? Math.max(16, +$(".wb-size").value * 4)
          : tool === "highlighter"
            ? +$(".wb-size").value * 2
            : +$(".wb-size").value,
      points: [p],
      ...(tool === "text" ? { text: $(".wb-text").value } : {}),
    };
  }
  function addText(p) {
    const item = makeItem("text", p);
    item.width = Math.min(96, item.width);
    if (!item.text) {
      status("Enter a text label first.");
      $(".wb-text").focus();
      return;
    }
    try {
      model.add(item);
      refresh("Text added.");
    } catch (e) {
      status(e.message);
    }
  }
  function erase(p) {
    for (const item of model.items)
      if (hitTest(item, p, Math.max(8, +$(".wb-size").value)))
        eraseIds.add(item.id);
    refresh(`${eraseIds.size} object(s) marked for erasing.`);
  }
  function down(e) {
    if (!acceptsPointer(e, $(".wb-pen-only").checked, active)) return;
    e.preventDefault();
    input.focus({ preventScroll: true });
    const tool = pointerTool(e, $(".wb-tool").value),
      p = point(e);
    if (tool === "text") {
      addText(p);
      return;
    }
    active = e.pointerId;
    input.setPointerCapture(e.pointerId);
    draft = makeItem(tool, p);
    painted = 0;
    if (tool === "eraser") erase(p);
    else schedule();
  }
  function move(e) {
    if (active !== e.pointerId || !draft) return;
    e.preventDefault();
    const samples =
      typeof e.getCoalescedEvents === "function" ? e.getCoalescedEvents() : [];
    for (const sample of samples.length ? samples : [e]) {
      const p = point(sample);
      if (draft.tool === "eraser") {
        erase(p);
        continue;
      }
      if (["pen", "highlighter"].includes(draft.tool)) {
        if (draft.points.length >= LIMITS.stroke) {
          status("Stroke point limit reached; lift the pen to continue.");
          break;
        }
        const previous = draft.points.at(-1);
        if (
          Math.hypot(previous.x - p.x, previous.y - p.y) >= 0.25 ||
          Math.abs(previous.p - p.p) > 0.03
        )
          draft.points.push(p);
      } else draft.points = [draft.points[0], p];
    }
    schedule();
  }
  function finish(e, cancelled = false) {
    if (active !== e.pointerId) return;
    // pointerup pressure is often zero: keep the last contact sample.
    const was = active;
    active = null;
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    try {
      if (!cancelled && draft) {
        if (draft.tool === "eraser") model.remove(eraseIds);
        else model.add(draft);
      }
    } catch (error) {
      status(error.message);
      draft = null;
      eraseIds.clear();
      clearInk();
      refresh(error.message);
      return;
    } finally {
      if (input.hasPointerCapture(was)) input.releasePointerCapture(was);
    }
    draft = null;
    eraseIds.clear();
    clearInk();
    refresh(cancelled ? "Stroke cancelled." : undefined);
  }
  const controller = new AbortController(),
    on = (node, type, fn) =>
      node.addEventListener(type, fn, { signal: controller.signal });
  on(input, "pointerdown", down);
  on(input, "pointermove", move);
  on(input, "pointerup", (e) => finish(e));
  on(input, "pointercancel", (e) => finish(e, true));
  on(input, "lostpointercapture", (e) => finish(e, true));
  on(input, "contextmenu", (e) => e.preventDefault());
  function cancel() {
    if (active !== null) finish({ pointerId: active }, true);
  }
  function insertSnapshot() {
    if (props.insertable !== true) return;
    const drawing = model.snapshot();
    const revision = state.commits.length + 1;
    state.commits.push({
      revision,
      drawing,
      svg: drawingSvg(drawing),
      alt: props.alt || `Whiteboard snapshot ${revision}`,
      outputId: props.output_id || "",
    });
    // Keep an accidental repeated-click session bounded while preserving the
    // editable drawing on the board itself.
    if (state.commits.length > 12) state.commits.shift();
    refresh(`Snapshot ${revision} inserted below the board.`);
  }
  function open(value) {
    cancel();
    state.open = value;
    $(".wb-panel").hidden = !value;
    $(".wb-spawn").hidden = value;
    if (value) {
      refresh();
      $(".wb-tool").focus();
    } else $(".wb-spawn").focus();
  }
  on($(".wb-spawn"), "click", () => open(true));
  on($(".wb-size"), "input", () => {
    $(".wb-size-label").value = $(".wb-size").value;
  });
  on($(".wb-paper"), "change", () => {
    cancel();
    d.background = $(".wb-paper").value;
    refresh();
  });
  on(root, "keydown", (e) => {
    // Whiteboard keys never navigate the underlying presentation.
    e.stopPropagation();
    if (e.target.matches("input,select,textarea")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      cancel();
      e.shiftKey ? model.redo() : model.undo();
      refresh();
    }
    if (e.key === "Escape" && !document.fullscreenElement) open(false);
  });
  const objectUrls = new Set();
  function download(blob, extension) {
    for (const previous of objectUrls) URL.revokeObjectURL(previous);
    objectUrls.clear();
    const url = URL.createObjectURL(blob);
    objectUrls.add(url);
    const a = $(".wb-download a");
    a.href = url;
    a.download = `whiteboard.${extension}`;
    a.textContent = `Download ${extension.toUpperCase()}`;
    $(".wb-download").hidden = false;
    a.click();
    status(
      `${extension.toUpperCase()} ready. Use the download link if saving did not start.`,
    );
  }
  on(root, "click", async (e) => {
    const action = e.target.closest("[data-action]")?.dataset.action;
    if (!action) return;
    cancel();
    try {
      if (action === "close") {
        if (document.fullscreenElement === root)
          await document.exitFullscreen();
        open(false);
      } else if (action === "fullscreen") {
        if (document.fullscreenElement === root)
          await document.exitFullscreen();
        else if (root.requestFullscreen) await root.requestFullscreen();
        else status("Full screen is unavailable; use browser zoom.");
      } else if (action === "undo" || action === "redo" || action === "clear") {
        model[action]();
        refresh();
      } else if (action === "insert") {
        insertSnapshot();
      } else if (action === "text")
        addText({ x: d.width / 2, y: d.height / 2, p: 0.5 });
      else if (action === "svg")
        download(new Blob([drawingSvg(d)], { type: "image/svg+xml" }), "svg");
      else if (action === "json")
        download(
          new Blob([JSON.stringify(model.snapshot())], {
            type: "application/json",
          }),
          "json",
        );
      else if (action === "png")
        base.toBlob((blob) => {
          if (blob && !disposed) download(blob, "png");
        }, "image/png");
    } catch (error) {
      status(error.message);
    }
  });
  on($(".wb-file"), "change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 32000000) throw new Error("Drawing file exceeds 32 MB.");
      const next = validateDrawing(JSON.parse(await file.text()));
      if (disposed) return;
      if (next.width !== d.width || next.height !== d.height)
        throw new Error(
          `Drawing must use this board's ${d.width} × ${d.height} coordinates.`,
        );
      cancel();
      model.command(
        model.items.map((item, index) => ({ item, index })),
        next.items.map((item, index) => ({ item, index })),
      );
      d.background = next.background;
      $(".wb-paper").value = d.background;
      refresh("Drawing loaded. Undo restores previous objects.");
    } catch (error) {
      if (!disposed) status(error.message);
    } finally {
      e.target.value = "";
    }
  });
  refresh();
  if (state.open) {
    $(".wb-panel").hidden = false;
    $(".wb-spawn").hidden = true;
  }
  return () => {
    state.settings = { penOnly: $(".wb-pen-only").checked };
    for (const name of ["tool", "color", "size", "text"])
      state.settings[name] = $(".wb-" + name).value;
    disposed = true;
    cancel();
    controller.abort();
    if (frame) cancelAnimationFrame(frame);
    for (const url of objectUrls) URL.revokeObjectURL(url);
    base.width = 0;
    input.width = 0;
    root.remove();
  };
}
