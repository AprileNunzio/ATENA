import { reducedMotion, svg } from "../../core/dom.js";

const W = 1240, H = 540, NODE_W = 172, NODE_H = 76, MARGIN = 40;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function edgePath(a, b) {
  if (Math.abs(b.y - a.y) > 60 && Math.abs(b.x - a.x) < 140) {
    const dir = b.y > a.y ? 1 : -1, y1 = a.y + (NODE_H / 2) * dir, y2 = b.y - (NODE_H / 2) * dir, d = (y2 - y1) / 2;
    return `M${a.x} ${y1}C${a.x} ${y1 + d} ${b.x} ${y2 - d} ${b.x} ${y2}`;
  }
  const dir = b.x >= a.x ? 1 : -1, x1 = a.x + (NODE_W / 2) * dir, x2 = b.x - (NODE_W / 2) * dir;
  const d = Math.max(40, Math.abs(x2 - x1) / 2) * dir;
  return `M${x1} ${a.y}C${x1 + d} ${a.y} ${x2 - d} ${b.y} ${x2} ${b.y}`;
}

const short = (text, max = 20) => (text.length > max ? `${text.slice(0, max - 1)}…` : text);

export class FlowCanvas {
  constructor({ onSelect, onMove }) {
    this.onSelect = onSelect;
    this.onMove = onMove;
    this.el = svg("svg", { class: "flow-svg", viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": "Diagramma del flusso di ragionamento" });
    this.points = new Map();
    this.groups = new Map();
    this.paths = new Map();
    this.drag = null;
  }

  point(event) {
    return new DOMPoint(event.clientX, event.clientY).matrixTransform(this.el.getScreenCTM().inverse());
  }

  render({ nodes, edges, picks, positions, selected, editable, current }) {
    this.nodes = nodes;
    this.edges = edges;
    this.el.replaceChildren(
      svg("defs", {},
        svg("filter", { id: "nx-glow", x: "-30%", y: "-30%", width: "160%", height: "160%" },
          svg("feGaussianBlur", { stdDeviation: "4", result: "b" }),
          svg("feMerge", {}, svg("feMergeNode", { in: "b" }), svg("feMergeNode", { in: "SourceGraphic" }))),
        svg("pattern", { id: "nx-dots", width: "24", height: "24", patternUnits: "userSpaceOnUse" }, svg("circle", { class: "fdot", cx: "2", cy: "2", r: "1.2" }))),
      svg("rect", { x: 0, y: 0, width: W, height: H, fill: "url(#nx-dots)" }));
    const edgeLayer = svg("g"), particleLayer = svg("g"), nodeLayer = svg("g");
    this.particles = particleLayer;
    this.el.append(edgeLayer, particleLayer, nodeLayer);
    for (const node of nodes) {
      const [x, y] = positions[node.id] || [node.x, node.y];
      this.points.set(node.id, { x, y });
    }
    for (const [a, b] of edges) {
      const path = svg("path", { class: "edge", d: edgePath(this.points.get(a), this.points.get(b)) });
      this.paths.set(`${a}>${b}`, path);
      edgeLayer.append(path);
    }
    for (const node of nodes) nodeLayer.append(this.nodeGroup(node, picks[node.id], node.id === selected, editable, current?.[node.id]));
  }

  nodeGroup(node, pick, isSelected, editable, live) {
    const { x, y } = this.points.get(node.id);
    const algorithm = node.algorithms.find((a) => a.id === pick);
    const label = algorithm ? algorithm.name : "Personalizzato";
    const changed = pick && live !== undefined && pick !== live;
    const g = svg("g", {
      class: `fn${node.locked ? " locked" : ""}${isSelected ? " sel" : ""}${changed ? " changed" : ""}${node.editable ? "" : " fixed"}`,
      transform: `translate(${x - NODE_W / 2} ${y - NODE_H / 2})`, tabindex: "0", role: "button",
      "aria-label": `${node.label}: ${label}${changed ? ", modificato nella bozza" : ""}`,
    },
    svg("rect", { width: NODE_W, height: NODE_H, rx: 16 }),
    svg("text", { class: "ng", x: 16, y: 46 }, node.glyph),
    svg("text", { class: "nl", x: 46, y: 32 }, node.label),
    svg("text", { class: "na", x: 46, y: 52 }, short(label)),
    node.locked ? svg("text", { class: "nk", x: NODE_W - 22, y: 22 }, "⚿") : null,
    changed ? svg("text", { class: "nc", x: 46, y: 68 }, "modificato") : null);
    g.addEventListener("pointerdown", (event) => {
      if (!editable) { this.onSelect(node.id); return; }
      const p = this.point(event), here = this.points.get(node.id);
      this.drag = { id: node.id, dx: p.x - here.x, dy: p.y - here.y, sx: p.x, sy: p.y, moved: false };
      try { g.setPointerCapture(event.pointerId); } catch { this.drag = null; }
    });
    g.addEventListener("pointermove", (event) => {
      if (!this.drag || this.drag.id !== node.id) return;
      const p = this.point(event);
      if (Math.hypot(p.x - this.drag.sx, p.y - this.drag.sy) > 4) this.drag.moved = true;
      if (this.drag.moved) this.move(node.id, p.x - this.drag.dx, p.y - this.drag.dy, g);
    });
    g.addEventListener("pointerup", () => {
      const drag = this.drag;
      this.drag = null;
      if (!drag || drag.id !== node.id) return;
      if (drag.moved) this.onMove(node.id, this.points.get(node.id));
      else this.onSelect(node.id);
    });
    g.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); this.onSelect(node.id); return; }
      const step = { ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10] }[event.key];
      if (!step || !editable) return;
      event.preventDefault();
      const here = this.points.get(node.id);
      this.move(node.id, here.x + step[0], here.y + step[1], g);
      this.onMove(node.id, this.points.get(node.id));
    });
    this.groups.set(node.id, g);
    return g;
  }

  move(id, x, y, group) {
    const point = { x: Math.round(clamp(x, MARGIN + NODE_W / 2 - 40, W - MARGIN - NODE_W / 2 + 40)), y: Math.round(clamp(y, MARGIN, H - MARGIN)) };
    this.points.set(id, point);
    group.setAttribute("transform", `translate(${point.x - NODE_W / 2} ${point.y - NODE_H / 2})`);
    for (const [a, b] of this.edges) {
      if (a === id || b === id) this.paths.get(`${a}>${b}`).setAttribute("d", edgePath(this.points.get(a), this.points.get(b)));
    }
  }

  mark(id, state) {
    const g = this.groups.get(id);
    if (!g) return;
    g.classList.toggle("active", state === "active");
    g.classList.toggle("done", state === "done");
  }

  async particle(a, b, ms) {
    const path = this.paths.get(`${a}>${b}`);
    if (!path) return;
    path.classList.add("hot");
    if (reducedMotion()) return;
    const length = path.getTotalLength(), dot = svg("circle", { class: "particle", r: 5 });
    this.particles.append(dot);
    await new Promise((resolve) => {
      const start = performance.now();
      const step = (now) => {
        const k = Math.min(1, (now - start) / ms), p = path.getPointAtLength(length * k);
        dot.setAttribute("cx", p.x);
        dot.setAttribute("cy", p.y);
        if (k < 1) requestAnimationFrame(step); else resolve();
      };
      requestAnimationFrame(step);
    });
    dot.remove();
  }

  reset() {
    this.groups.forEach((g) => g.classList.remove("active", "done"));
    this.paths.forEach((p) => p.classList.remove("hot"));
  }
}
