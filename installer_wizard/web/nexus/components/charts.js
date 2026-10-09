import { svg } from "../core/dom.js";

const CIRCUMFERENCE = 2 * Math.PI * 26;

export function ring(value, label) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  const node = svg("svg", { class: "ring", viewBox: "0 0 64 64", role: "img", "aria-label": `${label}: ${pct} per cento` },
    svg("circle", { class: "track", cx: 32, cy: 32, r: 26 }),
    svg("circle", { class: "value", cx: 32, cy: 32, r: 26, "stroke-dasharray": `${(CIRCUMFERENCE * pct) / 100} ${CIRCUMFERENCE}` }),
    svg("text", { x: 32, y: 37 }, `${pct}%`));
  return node;
}

export function sparkline(values, { max = 100, width = 200, height = 38 } = {}) {
  const node = svg("svg", { class: "spark", viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  if (values.length < 2) return node;
  const step = width / (values.length - 1);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${(height - (Math.min(v, max) / max) * (height - 4) - 2).toFixed(1)}`);
  node.append(
    svg("polygon", { class: "spark-fill", points: `0,${height} ${points.join(" ")} ${width},${height}` }),
    svg("polyline", { class: "spark-line", points: points.join(" ") }),
    svg("circle", { class: "spark-dot", cx: points.at(-1).split(",")[0], cy: points.at(-1).split(",")[1], r: 2.6 }));
  return node;
}

export class Series {
  constructor(size = 40) {
    this.size = size;
    this.values = [];
  }

  push(value) {
    if (!Number.isFinite(value)) return;
    this.values.push(value);
    if (this.values.length > this.size) this.values.shift();
  }
}
