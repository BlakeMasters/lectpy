/**
 * Dependency-free synchronized trajectory/response playback.
 *
 * The renderer is deliberately mount/unmount based so the static viewer and
 * the React shell consume the same component without sharing React internals.
 * Props are treated as untrusted data and normalized again at the browser
 * boundary even though the Python authoring API already bounds them.
 */

const SVG_NS = "http://www.w3.org/2000/svg";
const MAX_SERIES = 6;
const MAX_PANELS = 3;
const MAX_STEPS = 400;
let nextInstanceId = 0;

const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function label(value, fallback) {
  return typeof value === "string" && value.trim() ? value.slice(0, 160) : fallback;
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function normalizePoint(value) {
  if (Array.isArray(value)) {
    return { x: finite(value[0]), y: finite(value[1]) };
  }
  const point = value && typeof value === "object" ? value : {};
  return { x: finite(point.x), y: finite(point.y) };
}

function normalizeStepTrigger(raw) {
  const source = raw && typeof raw.step_trigger === "object" ? raw.step_trigger : null;
  return {
    autoplayOnStep: Boolean(source?.autoplay_on_step),
    restartOnEnter: Boolean(source?.restart_on_enter),
    pauseOnLeave: source ? source.pause_on_leave !== false : false,
  };
}

function normalizeProps(rawProps) {
  const raw = rawProps && typeof rawProps === "object" ? rawProps : {};
  const rawTrajectory = raw.trajectory && typeof raw.trajectory === "object" ? raw.trajectory : {};
  const rawTrajectorySeries = array(rawTrajectory.series).slice(0, MAX_SERIES);
  const trajectorySeries = rawTrajectorySeries.map((entry, index) => {
    const item = entry && typeof entry === "object" ? entry : {};
    const points = array(item.points).slice(0, MAX_STEPS + 1).map(normalizePoint);
    while (points.length < 2) points.push(points[points.length - 1] || { x: 0, y: 0 });
    return {
      id: label(item.id, `trajectory-${index + 1}`),
      label: label(item.label, `trajectory ${index + 1}`),
      points,
    };
  });
  if (!trajectorySeries.length) {
    trajectorySeries.push({
      id: "trajectory-1",
      label: "trajectory",
      points: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
    });
  }

  const inferredSteps = Math.max(...trajectorySeries.map((series) => series.points.length - 1), 1);
  const stepCount = clamp(Math.round(finite(raw.step_count, inferredSteps)), 1, MAX_STEPS);
  const rawPanels = array(raw.responses).slice(0, MAX_PANELS);
  const responses = rawPanels.map((panel, panelIndex) => {
    const item = panel && typeof panel === "object" ? panel : {};
    const rawSeries = array(item.series).slice(0, MAX_SERIES);
    const series = rawSeries.map((entry, index) => {
      const source = entry && typeof entry === "object" ? entry : {};
      const values = array(source.values).slice(0, stepCount + 1).map((value) => finite(value));
      while (values.length < stepCount + 1) values.push(values[values.length - 1] || 0);
      return {
        id: label(source.id, `response-${index + 1}`),
        label: label(source.label, `response ${index + 1}`),
        values,
      };
    });
    if (!series.length) series.push({ id: "response-1", label: "response", values: Array(stepCount + 1).fill(0) });
    const references = array(item.references).slice(0, MAX_SERIES).map((reference) => {
      const source = reference && typeof reference === "object" ? reference : {};
      const tone = typeof source.tone === "string" && (/^series-[1-6]$/.test(source.tone) || source.tone === "muted")
        ? source.tone
        : "muted";
      return {
        value: finite(source.value),
        label: label(source.label, "reference"),
        tone,
      };
    });
    return {
      id: label(item.id, `panel-${panelIndex + 1}`),
      title: label(item.title, `Response ${panelIndex + 1}`),
      yLabel: label(item.y_label, "value"),
      series,
      references,
    };
  });
  if (!responses.length) {
    responses.push({
      id: "panel-1",
      title: "Response",
      yLabel: "value",
      series: [{ id: "response-1", label: "response", values: Array(stepCount + 1).fill(0) }],
      references: [],
    });
  }

  const rawTarget = rawTrajectory.target && typeof rawTrajectory.target === "object" ? rawTrajectory.target : null;
  const target = rawTarget
    ? { x: finite(rawTarget.x), y: finite(rawTarget.y), label: label(rawTarget.label, "equilibrium") }
    : null;

  return {
    title: label(raw.title, "Step playback"),
    alt: label(raw.alt, "Synchronized step playback figure."),
    stepCount,
    stepTrigger: normalizeStepTrigger(raw),
    trajectory: {
      xLabel: label(rawTrajectory.x_label, "x"),
      yLabel: label(rawTrajectory.y_label, "y"),
      series: trajectorySeries,
      contours: array(rawTrajectory.contours).slice(0, 12).map((contour) => {
        const source = contour && typeof contour === "object" ? contour : {};
        return { level: finite(source.level ?? contour), dashed: Boolean(source.dashed) };
      }),
      target,
    },
    responses,
  };
}

function htmlElement(tag, attrs = {}) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (key === "className") node.className = String(value);
    else if (key === "textContent") node.textContent = String(value);
    else node.setAttribute(key, String(value));
  });
  return node;
}

function svgElement(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (value !== undefined && value !== null) node.setAttribute(key, String(value));
  });
  return node;
}

function svgText(parent, x, y, value, className = "", attrs = {}) {
  const node = svgElement("text", {
    x,
    y,
    class: `step-playback-svg-text ${className}`.trim(),
    "font-size": 12,
    "font-weight": 400,
    "dominant-baseline": "middle",
    ...attrs,
  });
  node.textContent = String(value);
  parent.appendChild(node);
  return node;
}

function setSvgSize(svg, container, ratio, minHeight = 300) {
  const width = Math.max(1, Math.floor(container.getBoundingClientRect().width || 640));
  const height = Math.max(minHeight, Math.min(500, Math.floor(width * ratio)));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  return { width, height };
}

function extent(values) {
  const finiteValues = values.map(Number).filter(Number.isFinite);
  if (!finiteValues.length) return [0, 1];
  return [Math.min(...finiteValues), Math.max(...finiteValues)];
}

function paddedDomain(values, fraction = 0.08, floor = -Infinity) {
  let [lo, hi] = extent(values);
  if (lo === hi) {
    lo -= 0.5;
    hi += 0.5;
  }
  const pad = (hi - lo) * fraction;
  return [Math.max(floor, lo - pad), hi + pad];
}

function linear(domain, range) {
  return (value) => range[0] + ((value - domain[0]) / (domain[1] - domain[0])) * (range[1] - range[0]);
}

function ticks(domain, count = 4) {
  const [lo, hi] = domain;
  if (count < 2 || !Number.isFinite(lo) || !Number.isFinite(hi) || lo === hi) return [lo];
  return Array.from({ length: count }, (_, index) => lo + ((hi - lo) * index) / (count - 1));
}

function formatTick(value) {
  return Number(value).toFixed(1);
}

function smoothPath(points, sx, sy) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${sx(points[0].x)} ${sy(points[0].y)}`;
  let d = `M ${sx(points[0].x)} ${sy(points[0].y)}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[index - 1] || points[index];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[index + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${sx(c1x)} ${sy(c1y)}, ${sx(c2x)} ${sy(c2y)}, ${sx(p2.x)} ${sy(p2.y)}`;
  }
  return d;
}

function pointAt(points, progress) {
  if (points.length === 1) return points[0];
  const position = clamp(progress, 0, 1) * (points.length - 1);
  const index = Math.min(points.length - 2, Math.floor(position));
  const fraction = position - index;
  const first = points[index];
  const second = points[index + 1];
  return {
    x: first.x + (second.x - first.x) * fraction,
    y: first.y + (second.y - first.y) * fraction,
  };
}

function partialPoints(points, progress) {
  const end = clamp(progress, 0, 1) * (points.length - 1);
  const visible = points.filter((_, index) => index <= end).map((point) => ({ ...point }));
  const current = pointAt(points, progress);
  if (!visible.length) visible.push({ ...points[0] });
  const last = visible[visible.length - 1];
  if (last.x !== current.x || last.y !== current.y) visible.push(current);
  return visible;
}

function seriesClass(index) {
  return `step-playback-series-${(index % MAX_SERIES) + 1}`;
}

function addAxes(group, plot, xTicks, yTicks, sx, sy, xLabel, yLabel, showXLabels) {
  const grid = svgElement("g", { "aria-hidden": "true" });
  xTicks.forEach((tick) => {
    const x = sx(tick);
    grid.appendChild(svgElement("line", {
      x1: x, x2: x, y1: plot.y, y2: plot.y + plot.height, class: "step-playback-grid-line",
    }));
    if (showXLabels) svgText(grid, x, plot.y + plot.height + 17, formatTick(tick), "step-playback-muted", { "text-anchor": "middle" });
  });
  yTicks.forEach((tick) => {
    const y = sy(tick);
    grid.appendChild(svgElement("line", {
      x1: plot.x, x2: plot.x + plot.width, y1: y, y2: y, class: "step-playback-grid-line",
    }));
    svgText(grid, plot.x - 10, y, formatTick(tick), "step-playback-muted", { "text-anchor": "end" });
  });
  group.appendChild(grid);
  group.appendChild(svgElement("rect", {
    x: plot.x, y: plot.y, width: plot.width, height: plot.height, class: "step-playback-frame",
    "data-chart-frame": "true",
  }));
  if (xLabel) svgText(group, plot.x + plot.width / 2, plot.y + plot.height + 36, xLabel, "step-playback-axis-title", { "text-anchor": "middle", "data-axis": "x" });
  if (yLabel) svgText(group, 16, plot.y + plot.height / 2, yLabel, "step-playback-axis-title", { "text-anchor": "middle", "data-axis": "y", transform: `rotate(-90 16 ${plot.y + plot.height / 2})` });
}

function addSvgTitle(svg, id, title, description) {
  const titleNode = svgElement("title", { id });
  titleNode.textContent = title;
  svg.appendChild(titleNode);
  const desc = svgElement("desc", { id: `${id}-description` });
  desc.textContent = description;
  svg.appendChild(desc);
  svg.setAttribute("aria-labelledby", `${id} ${id}-description`);
}

function drawTrajectory(svg, container, data, progress, instanceId) {
  const { width, height } = setSvgSize(svg, container, 0.72);
  svg.replaceChildren();
  addSvgTitle(svg, `${instanceId}-trajectory-title`, "State-space trajectory", data.alt);
  const margin = { top: 22, right: 20, bottom: 48, left: 58 };
  const plot = { x: margin.left, y: margin.top, width: width - margin.left - margin.right, height: height - margin.top - margin.bottom };
  const trajectories = data.trajectory.series;
  const xValues = trajectories.flatMap((series) => series.points.map((point) => point.x));
  const yValues = trajectories.flatMap((series) => series.points.map((point) => point.y));
  if (data.trajectory.target) {
    xValues.push(data.trajectory.target.x);
    yValues.push(data.trajectory.target.y);
  }
  const xDomain = paddedDomain(xValues, 0.08);
  const yDomain = paddedDomain(yValues, 0.08);
  const sx = linear(xDomain, [plot.x, plot.x + plot.width]);
  const sy = linear(yDomain, [plot.y + plot.height, plot.y]);
  const xTicks = ticks(xDomain, 4);
  const yTicks = ticks(yDomain, 4);
  const clipId = `${instanceId}-trajectory-clip`;
  const defs = svgElement("defs");
  const clip = svgElement("clipPath", { id: clipId });
  clip.appendChild(svgElement("rect", { x: plot.x, y: plot.y, width: plot.width, height: plot.height }));
  defs.appendChild(clip);
  svg.appendChild(defs);
  const group = svgElement("g");
  addAxes(group, plot, xTicks.length ? xTicks : ticks(xDomain, 4), yTicks.length ? yTicks : ticks(yDomain, 4), sx, sy, data.trajectory.xLabel, data.trajectory.yLabel, true);
  if (data.trajectory.contours.length) svgText(group, plot.x + 8, plot.y + 14, "product contours", "step-playback-muted", { "font-weight": 500 });
  svgText(group, plot.x + 8, plot.y + 30, "one shared step clock", "step-playback-muted");

  const contourGroup = svgElement("g", { "clip-path": `url(#${clipId})`, "aria-hidden": "true" });
  data.trajectory.contours.forEach((contour) => {
    const branches = [[], []];
    for (let index = 0; index <= 100; index += 1) {
      const x = xDomain[0] + ((xDomain[1] - xDomain[0]) * index) / 100;
      if (Math.abs(x) >= 0.05) branches[x < 0 ? 0 : 1].push({ x, y: contour.level / x });
    }
    branches.filter((points) => points.length).forEach((points) => contourGroup.appendChild(svgElement("path", {
      d: smoothPath(points, sx, sy), class: "step-playback-contour",
      "stroke-dasharray": contour.dashed ? "3 5" : undefined,
    })));
  });
  group.appendChild(contourGroup);

  const trailGroup = svgElement("g", { "clip-path": `url(#${clipId})` });
  trajectories.forEach((series, seriesIndex) => {
    const points = series.points.map((point, index) => ({ ...point, p: index / (series.points.length - 1) }));
    const color = seriesClass(seriesIndex);
    trailGroup.appendChild(svgElement("path", { d: smoothPath(points, sx, sy), class: `${color} step-playback-ghost-line` }));
    trailGroup.appendChild(svgElement("path", { d: smoothPath(partialPoints(points, progress), sx, sy), class: `${color} step-playback-live-line` }));
  });
  group.appendChild(trailGroup);

  const start = trajectories[0].points[0];
  group.appendChild(svgElement("circle", { cx: sx(start.x), cy: sy(start.y), r: 4.5, class: "step-playback-start" }));
  trajectories.forEach((series, seriesIndex) => {
    const points = series.points.map((point, index) => ({ ...point, p: index / (series.points.length - 1) }));
    const current = pointAt(points, progress);
    const color = seriesClass(seriesIndex);
    const marker = svgElement("circle", {
      cx: sx(current.x), cy: sy(current.y), r: 6, class: `${color} step-playback-current-marker`,
      role: "img", "aria-label": `${series.label}: (${current.x.toFixed(2)}, ${current.y.toFixed(2)})`,
    });
    const title = svgElement("title");
    title.textContent = `${series.label}: (${current.x.toFixed(2)}, ${current.y.toFixed(2)})`;
    marker.appendChild(title);
    group.appendChild(marker);
  });
  if (data.trajectory.target) {
    const target = data.trajectory.target;
    group.appendChild(svgElement("circle", { cx: sx(target.x), cy: sy(target.y), r: 7, class: "step-playback-target" }));
    const alignEnd = sx(target.x) > plot.x + plot.width / 2;
    svgText(group, clamp(sx(target.x) + (alignEnd ? -9 : 9), plot.x + 8, plot.x + plot.width - 8), clamp(sy(target.y) - 8, plot.y + 10, plot.y + plot.height - 10), target.label, "step-playback-muted", { "text-anchor": alignEnd ? "end" : "start", "font-weight": 500 });
  }
  svg.appendChild(group);
}

function drawResponses(svg, container, data, progress, instanceId) {
  const panelCount = data.responses.length;
  const { width, height } = setSvgSize(svg, container, 0.86, 68 + 115 * panelCount + 32 * (panelCount - 1));
  svg.replaceChildren();
  addSvgTitle(svg, `${instanceId}-responses-title`, "Synchronized response curves", data.alt);
  const margin = { top: 20, right: 22, bottom: 48, left: 78 };
  const gap = 32;
  const panelHeight = Math.max(115, (height - margin.top - margin.bottom - gap * (panelCount - 1)) / panelCount);
  const plotWidth = width - margin.left - margin.right;
  const xDomain = paddedDomain([0, data.stepCount], 0.02, 0);
  const sx = linear(xDomain, [margin.left, margin.left + plotWidth]);
  const xTicks = Array.from(new Set([0, Math.round(data.stepCount / 3), Math.round((2 * data.stepCount) / 3), data.stepCount]));
  const defs = svgElement("defs");
  svg.appendChild(defs);
  const group = svgElement("g");
  data.responses.forEach((panel, panelIndex) => {
    const plot = { x: margin.left, y: margin.top + panelIndex * (panelHeight + gap), width: plotWidth, height: panelHeight };
    const allValues = panel.series.flatMap((series) => series.values).concat(panel.references.map((reference) => reference.value));
    const yDomain = paddedDomain(allValues, 0.10);
    const sy = linear(yDomain, [plot.y + plot.height, plot.y]);
    const clipId = `${instanceId}-response-clip-${panelIndex}`;
    const clip = svgElement("clipPath", { id: clipId });
    clip.appendChild(svgElement("rect", { x: plot.x, y: plot.y, width: plot.width, height: plot.height }));
    defs.appendChild(clip);
    addAxes(group, plot, xTicks, ticks(yDomain, 4), sx, sy, panelIndex === panelCount - 1 ? "step t" : "", panel.yLabel, panelIndex === panelCount - 1);
    svgText(group, plot.x + 8, plot.y + 14, panel.title, "step-playback-panel-title", { "font-weight": 500 });

    const referenceGroup = svgElement("g", { "clip-path": `url(#${clipId})` });
    panel.references.forEach((reference) => {
      const color = reference.tone === "muted" ? "step-playback-muted-stroke" : `step-playback-${reference.tone}`;
      referenceGroup.appendChild(svgElement("line", { x1: plot.x, x2: plot.x + plot.width, y1: sy(reference.value), y2: sy(reference.value), class: `${color} step-playback-reference-line` }));
    });
    group.appendChild(referenceGroup);

    const lineGroup = svgElement("g", { "clip-path": `url(#${clipId})` });
    panel.series.forEach((series, seriesIndex) => {
      const points = series.values.map((value, index) => ({ x: index, y: value, p: index / (series.values.length - 1) }));
      const color = seriesClass(seriesIndex);
      lineGroup.appendChild(svgElement("path", { d: smoothPath(points, sx, sy), class: `${color} step-playback-ghost-line` }));
      lineGroup.appendChild(svgElement("path", { d: smoothPath(partialPoints(points, progress), sx, sy), class: `${color} step-playback-live-line` }));
      const current = pointAt(points, progress);
      const marker = svgElement("circle", {
        cx: sx(current.x), cy: sy(current.y), r: 5.5, class: `${color} step-playback-current-marker`,
        role: "img", "aria-label": `${series.label}: ${current.y.toFixed(3)}`,
      });
      const title = svgElement("title");
      title.textContent = `${series.label}: ${current.y.toFixed(3)}`;
      marker.appendChild(title);
      lineGroup.appendChild(marker);
      svgText(group, plot.x + 8, plot.y + 14 + (seriesIndex + 1) * 16, series.label, color, { "font-weight": 500 });
    });
    group.appendChild(lineGroup);
    panel.references.forEach((reference, referenceIndex) => {
      const color = reference.tone === "muted" ? "step-playback-muted" : `step-playback-${reference.tone}`;
      const y = clamp(sy(reference.value) - 10 - referenceIndex * 14, plot.y + 10, plot.y + plot.height - 10);
      svgText(group, plot.x + plot.width - 6, y, reference.label, color, { "text-anchor": "end", "font-weight": 500 });
    });
  });
  svg.appendChild(group);
}

function phaseFor(progress) {
  if (progress <= 0) return "ready";
  if (progress >= 1) return "playback complete";
  return "playback in progress";
}

function buildFigure(shell, kind, title, muted, svgId) {
  const figure = htmlElement("figure", { className: "step-playback-figure", "aria-labelledby": `${svgId}-heading` });
  const heading = htmlElement("div", { className: "step-playback-figure-heading" });
  heading.append(
    htmlElement("strong", { id: `${svgId}-heading`, textContent: title }),
    htmlElement("span", { className: "step-playback-muted", textContent: muted }),
  );
  const wrap = htmlElement("div", { className: "step-playback-svg-wrap" });
  const svg = svgElement("svg", { id: svgId, role: "img" });
  wrap.appendChild(svg);
  figure.append(heading, wrap);
  shell.grid.appendChild(figure);
  return { wrap, svg };
}

function buildShell(host, data, instanceId) {
  const titleId = `${instanceId}-heading`;
  const section = htmlElement("section", { className: "step-playback", "aria-labelledby": titleId });
  const heading = htmlElement("div", { className: "step-playback-heading" });
  const headingCopy = htmlElement("div");
  headingCopy.append(
    htmlElement("div", { className: "step-playback-kicker", textContent: "Interactive figure" }),
    htmlElement("h2", { id: titleId, textContent: data.title }),
  );
  const readout = htmlElement("div", { className: "step-playback-readout", "aria-label": "Current playback position" });
  const stepReadout = htmlElement("strong", { className: "tabular-nums", textContent: `step 0 / ${data.stepCount}` });
  const tauReadout = htmlElement("span", { className: "tabular-nums", textContent: "τ = 0.00" });
  readout.append(stepReadout, htmlElement("span", { className: "step-playback-muted", textContent: "·" }), tauReadout);
  heading.append(headingCopy, readout);

  const controls = htmlElement("div", { className: "step-playback-controls", "aria-label": "Playback controls" });
  const playButton = htmlElement("button", { type: "button", className: "step-playback-button", "aria-pressed": "false" });
  const glyph = htmlElement("span", { className: "step-playback-glyph", "aria-hidden": "true", textContent: "▶" });
  const playLabel = htmlElement("span", { textContent: "Play" });
  playButton.append(glyph, playLabel);
  const rangeWrap = htmlElement("div", { className: "step-playback-range" });
  const rangeId = `${instanceId}-range`;
  const rangeLabel = htmlElement("label", { className: "step-playback-range-label", for: rangeId });
  const rangeOutput = htmlElement("output", { className: "tabular-nums", for: rangeId, textContent: `0 / ${data.stepCount}` });
  rangeLabel.append(htmlElement("span", { textContent: "Playback position" }), rangeOutput);
  const range = htmlElement("input", { id: rangeId, type: "range", min: "0", max: String(data.stepCount), step: "0.01", value: "0", "aria-label": "Playback position" });
  rangeWrap.append(rangeLabel, range);
  controls.append(playButton, rangeWrap);

  const grid = htmlElement("div", { className: "step-playback-grid" });
  const figureShell = { grid };
  const trajectory = buildFigure(figureShell, "trajectory", "State space", "trajectory", `${instanceId}-trajectory`);
  const legend = htmlElement("div", { className: "step-playback-legend", role: "list", "aria-label": "Trajectory series" });
  data.trajectory.series.forEach((series, index) => {
    const item = htmlElement("span", { role: "listitem", className: seriesClass(index) });
    item.append(
      htmlElement("span", { className: "step-playback-status-dot", "aria-hidden": "true" }),
      document.createTextNode(series.label),
    );
    legend.appendChild(item);
  });
  trajectory.wrap.after(legend);
  const responses = buildFigure(figureShell, "responses", "Responses", "same step clock", `${instanceId}-responses`);
  const status = htmlElement("div", { className: "step-playback-status" });
  const dot = htmlElement("span", { className: "step-playback-status-dot step-playback-series-2", "aria-hidden": "true" });
  const phase = htmlElement("span", { className: "step-playback-phase", "aria-live": "polite", textContent: "initialization" });
  const metrics = htmlElement("span", { className: "step-playback-metrics tabular-nums", textContent: "" });
  status.append(dot, phase, metrics);
  const alt = htmlElement("p", { className: "sr-only", textContent: data.alt });
  section.append(heading, controls, grid, status, alt);
  host.replaceChildren(section);
  host.classList.add("step-playback-host");
  return {
    section, grid, playButton, glyph, playLabel, range, rangeOutput, stepReadout, tauReadout, phase, metrics, dot,
    trajectory, responses,
  };
}

export function mountStepPlayback(host, rawProps, options = {}) {
  if (!(host instanceof HTMLElement)) return () => {};
  const data = normalizeProps(rawProps);
  const instanceId = `step-playback-${++nextInstanceId}`;
  const shell = buildShell(host, data, instanceId);
  let progress = 0;
  let playing = false;
  let active = false;
  let rafId = 0;
  let lastFrame = null;
  let lastPhaseStep = -1;
  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  const updateButton = () => {
    const atEnd = progress >= 1 - 1e-9;
    const text = playing ? "Pause" : atEnd ? "Replay" : "Play";
    shell.playButton.setAttribute("aria-pressed", String(playing));
    shell.playButton.setAttribute("aria-label", text);
    shell.glyph.textContent = playing ? "Ⅱ" : atEnd ? "↺" : "▶";
    shell.playLabel.textContent = text;
  };

  const render = () => {
    const step = Math.round(progress * data.stepCount);
    const trajectoryState = pointAt(data.trajectory.series[0].points, progress);
    const response = data.responses[0].series[0].values;
    const responseValue = response[Math.min(response.length - 1, Math.round(progress * (response.length - 1)))];
    shell.stepReadout.textContent = `step ${step} / ${data.stepCount}`;
    shell.tauReadout.textContent = `τ = ${progress.toFixed(2)}`;
    shell.range.value = String(progress * data.stepCount);
    shell.rangeOutput.textContent = `${step} / ${data.stepCount}`;
    shell.metrics.textContent = `state = (${trajectoryState.x.toFixed(2)}, ${trajectoryState.y.toFixed(2)}) · response = ${responseValue.toFixed(2)}`;
    if (step !== lastPhaseStep) {
      lastPhaseStep = step;
      const phase = phaseFor(progress);
      shell.phase.textContent = phase;
      shell.phase.setAttribute("aria-label", `Playback step ${step} of ${data.stepCount}: ${phase}`);
    }
    drawTrajectory(shell.trajectory.svg, shell.trajectory.wrap, data, progress, instanceId);
    drawResponses(shell.responses.svg, shell.responses.wrap, data, progress, instanceId);
  };

  const stop = () => {
    playing = false;
    if (rafId) window.cancelAnimationFrame(rafId);
    rafId = 0;
    shell.dot.className = "step-playback-status-dot step-playback-series-2";
    updateButton();
  };

  const frame = (now) => {
    if (!playing) return;
    if (lastFrame === null) lastFrame = now;
    const elapsed = now - lastFrame;
    const increment = reducedMotion ? Math.floor(elapsed / 260) / data.stepCount : elapsed / 7600;
    if (increment > 0) {
      lastFrame = reducedMotion ? now - (elapsed % 260) : now;
      progress = Math.min(1, progress + increment);
      render();
    }
    if (progress >= 1 - 1e-9) {
      progress = 1;
      render();
      stop();
      return;
    }
    rafId = window.requestAnimationFrame(frame);
  };

  const play = () => {
    if (playing) return;
    if (progress >= 1 - 1e-9) {
      progress = 0;
      render();
    }
    playing = true;
    lastFrame = null;
    shell.dot.className = "step-playback-status-dot step-playback-series-1";
    updateButton();
    rafId = window.requestAnimationFrame(frame);
  };
  const pause = () => stop();
  const replay = () => {
    progress = 0;
    lastFrame = null;
    lastPhaseStep = -1;
    render();
    play();
  };
  const onPlay = () => {
    if (playing) pause();
    else play();
  };
  const onRange = () => {
    stop();
    progress = clamp(finite(shell.range.value) / data.stepCount, 0, 1);
    render();
    updateButton();
  };
  const onControl = (event) => {
    const action = event.detail && typeof event.detail.action === "string"
      ? event.detail.action
      : "";
    if (action === "playback.play" || action === "play") play();
    else if (action === "playback.pause" || action === "pause") pause();
    else if (action === "playback.toggle" || action === "toggle") onPlay();
    else if (action === "playback.replay" || action === "replay") replay();
  };
  const setActive = (next, entered = false) => {
    const wasActive = active;
    active = Boolean(next);
    host.dataset.stepPlaybackActive = String(active);
    if (!active && wasActive && data.stepTrigger.pauseOnLeave) pause();
    if (active && (entered || !wasActive) && data.stepTrigger.autoplayOnStep) {
      if (data.stepTrigger.restartOnEnter) {
        progress = 0;
        lastFrame = null;
        lastPhaseStep = -1;
        render();
      }
      play();
    }
  };
  const onActive = (event) => {
    const next = event.detail && typeof event.detail.active === "boolean"
      ? event.detail.active
      : false;
    setActive(next, next && !active);
  };
  shell.playButton.addEventListener("click", onPlay);
  shell.range.addEventListener("input", onRange);
  host.addEventListener("lectpy:step-playback-control", onControl);
  host.addEventListener("lectpy:step-playback-active", onActive);

  const resizeObserver = typeof ResizeObserver === "function" ? new ResizeObserver(render) : null;
  if (resizeObserver) {
    resizeObserver.observe(shell.trajectory.wrap);
    resizeObserver.observe(shell.responses.wrap);
  } else {
    window.addEventListener("resize", render);
  }
  updateButton();
  render();
  setActive(Boolean(options.active), Boolean(options.active));

  return () => {
    stop();
    shell.playButton.removeEventListener("click", onPlay);
    shell.range.removeEventListener("input", onRange);
    host.removeEventListener("lectpy:step-playback-control", onControl);
    host.removeEventListener("lectpy:step-playback-active", onActive);
    if (resizeObserver) resizeObserver.disconnect();
    else window.removeEventListener("resize", render);
    host.replaceChildren();
  };
}

export { normalizeProps as normalizeStepPlaybackProps };
