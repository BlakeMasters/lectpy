/** Dependency-free structured UML renderer shared by static and React views. */
function umlEscape(value) {
  return String(value ?? "").replace(/[<>&"']/g, (c) => ({
    "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;",
  })[c]);
}

function label(value, fallback = "") {
  return typeof value === "string" ? value.slice(0, 240) : fallback;
}

function list(value, max = 24) {
  return Array.isArray(value) ? value.map((item) => label(item)).filter(Boolean).slice(0, max) : [];
}

function classEntries(spec) {
  return Array.isArray(spec?.classes)
    ? spec.classes.slice(0, 48).map((entry, index) => ({
      id: label(entry?.id || entry?.name, `class-${index + 1}`),
      name: label(entry?.name || entry?.id, `Class ${index + 1}`),
      attributes: list(entry?.attributes),
      methods: list(entry?.methods),
    }))
    : [];
}

function classSvg(spec) {
  const classes = classEntries(spec);
  const cols = Math.max(1, Math.min(3, classes.length || 1));
  const gapX = 54;
  const gapY = 54;
  const boxW = 252;
  const heights = classes.map((entry) => 54 + Math.max(entry.attributes.length, 1) * 24 + Math.max(entry.methods.length, 1) * 24);
  const rows = Math.max(1, Math.ceil(classes.length / cols));
  const rowHeights = Array.from({ length: rows }, (_, row) => Math.max(...heights.slice(row * cols, row * cols + cols), 150));
  const width = cols * boxW + (cols + 1) * gapX;
  const height = rowHeights.reduce((sum, value) => sum + value, 0) + (rows + 1) * gapY;
  const positions = new Map();
  let y = gapY;
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const index = row * cols + col;
      if (!classes[index]) continue;
      positions.set(classes[index].id, { x: gapX + col * (boxW + gapX), y, w: boxW, h: heights[index] });
    }
    y += rowHeights[row] + gapY;
  }
  const relations = Array.isArray(spec?.relations) ? spec.relations.slice(0, 96) : [];
  let content = `<defs><marker id="uml-arrow" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#334155"/></marker></defs>`;
  relations.forEach((relation) => {
    const from = positions.get(label(relation?.from));
    const to = positions.get(label(relation?.to));
    if (!from || !to) return;
    const x1 = from.x + from.w / 2;
    const y1 = from.y + from.h / 2;
    const x2 = to.x + to.w / 2;
    const y2 = to.y + to.h / 2;
    const kind = label(relation?.kind, "association");
    const dash = kind === "dependency" || kind === "realization" ? ' stroke-dasharray="7 5"' : "";
    content += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#334155" stroke-width="2"${dash} marker-end="url(#uml-arrow)"/>`;
    if (relation?.label) content += `<text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 8}" text-anchor="middle" font-size="14" fill="#334155">${umlEscape(label(relation.label))}</text>`;
  });
  classes.forEach((entry) => {
    const box = positions.get(entry.id);
    const attrY = box.y + 54;
    const methodY = attrY + Math.max(entry.attributes.length, 1) * 24;
    content += `<g class="uml-class"><rect x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" fill="#ffffff" stroke="#334155" stroke-width="2"/><rect x="${box.x}" y="${box.y}" width="${box.w}" height="54" fill="#e2e8f0" stroke="#334155" stroke-width="2"/><text x="${box.x + box.w / 2}" y="${box.y + 33}" text-anchor="middle" font-size="19" font-weight="700" fill="#0f172a">${umlEscape(entry.name)}</text><line x1="${box.x}" y1="${methodY}" x2="${box.x + box.w}" y2="${methodY}" stroke="#94a3b8"/>`;
    (entry.attributes.length ? entry.attributes : ["—"]).forEach((value, index) => {
      content += `<text x="${box.x + 14}" y="${attrY + 18 + index * 24}" font-size="14" fill="#334155">${umlEscape(value)}</text>`;
    });
    (entry.methods.length ? entry.methods : ["—"]).forEach((value, index) => {
      content += `<text x="${box.x + 14}" y="${methodY + 18 + index * 24}" font-size="14" fill="#334155">${umlEscape(value)}</text>`;
    });
    content += "</g>";
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="UML class diagram" class="uml-svg">${content}</svg>`;
}

function sequenceSvg(spec) {
  const participants = Array.isArray(spec?.participants)
    ? spec.participants.slice(0, 24).map((entry, index) => ({
      id: label(entry?.id || entry?.name || entry, `participant-${index + 1}`),
      name: label(entry?.name || entry?.id || entry, `Participant ${index + 1}`),
    }))
    : [];
  const messages = Array.isArray(spec?.messages) ? spec.messages.slice(0, 80) : [];
  const gap = 180;
  const left = 110;
  const width = Math.max(520, left * 2 + Math.max(1, participants.length - 1) * gap);
  const height = 120 + messages.length * 62 + 54;
  const positions = new Map(participants.map((participant, index) => [participant.id, left + index * gap]));
  let content = "";
  participants.forEach((participant, index) => {
    const x = left + index * gap;
    content += `<rect x="${x - 64}" y="24" width="128" height="42" rx="3" fill="#e2e8f0" stroke="#334155" stroke-width="2"/><text x="${x}" y="51" text-anchor="middle" font-size="16" font-weight="700" fill="#0f172a">${umlEscape(participant.name)}</text><line x1="${x}" y1="66" x2="${x}" y2="${height - 24}" stroke="#94a3b8" stroke-dasharray="7 6" stroke-width="2"/>`;
  });
  content += `<defs><marker id="uml-seq-arrow" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0 0L8 4L0 8Z" fill="#334155"/></marker></defs>`;
  messages.forEach((message, index) => {
    const x1 = positions.get(label(message?.from));
    const x2 = positions.get(label(message?.to));
    if (x1 == null || x2 == null) return;
    const y = 104 + index * 62;
    const dashed = label(message?.kind) === "return" ? ' stroke-dasharray="7 5"' : "";
    content += `<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="#334155" stroke-width="2"${dashed} marker-end="url(#uml-seq-arrow)"/><text x="${(x1 + x2) / 2}" y="${y - 9}" text-anchor="middle" font-size="14" fill="#334155">${umlEscape(label(message?.label, "message"))}</text>`;
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="UML sequence diagram" class="uml-svg">${content}</svg>`;
}

export function umlSvg(kind, spec) {
  return kind === "sequence" ? sequenceSvg(spec || {}) : classSvg(spec || {});
}

export function umlDescription(kind, spec) {
  if (kind === "sequence") {
    const participants = (spec?.participants || []).map((entry) => label(entry?.name || entry)).filter(Boolean);
    const messages = (spec?.messages || []).map((entry) => `${label(entry?.from)} → ${label(entry?.to)}: ${label(entry?.label, "message")}`).filter(Boolean);
    return `Sequence participants: ${participants.join(", ")}. ${messages.join("; ")}`;
  }
  const classes = classEntries(spec);
  const relations = (spec?.relations || []).map((entry) => `${label(entry?.from)} → ${label(entry?.to)}: ${label(entry?.label, label(entry?.kind, "association"))}`).filter(Boolean);
  return `Classes: ${classes.map((entry) => entry.name).join(", ")}. ${relations.join("; ")}`;
}
