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

const AXES = [["speed", "Velocità"], ["quality", "Qualità"], ["privacy", "Privacy"], ["saving", "Risparmio"]];

export function radar(traits, compare) {
  const W = 300, H = 200, cx = 150, cy = 100, r = 64;
  const angle = (i) => -Math.PI / 2 + (i * Math.PI) / 2;
  const points = (values) => AXES.map(([key], i) => {
    const k = Math.max(0, Math.min(5, values[key] || 0)) / 5;
    return `${(cx + Math.cos(angle(i)) * r * k).toFixed(1)},${(cy + Math.sin(angle(i)) * r * k).toFixed(1)}`;
  }).join(" ");
  const label = AXES.map(([key, name]) => `${name} ${Number(traits[key] || 0).toFixed(1)} su 5`).join(", ");
  const node = svg("svg", { class: "radar", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": label });
  for (let level = 1; level <= 5; level++) node.append(svg("polygon", { class: "radar-grid", points: points({ speed: level, quality: level, privacy: level, saving: level }) }));
  AXES.forEach(([, name], i) => {
    node.append(svg("line", { class: "radar-grid", x1: cx, y1: cy, x2: cx + Math.cos(angle(i)) * r, y2: cy + Math.sin(angle(i)) * r }));
    const x = cx + Math.cos(angle(i)) * (r + 10), y = cy + Math.sin(angle(i)) * (r + 12) + (i === 2 ? 8 : i === 0 ? -2 : 4);
    node.append(svg("text", { class: "radar-label", x, y, "text-anchor": i === 1 ? "start" : i === 3 ? "end" : "middle" }, name));
  });
  if (compare) node.append(svg("polygon", { class: "radar-compare", points: points(compare) }));
  node.append(svg("polygon", { class: "radar-value", points: points(traits) }));
  return node;
}
