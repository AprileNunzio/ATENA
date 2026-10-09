import { reducedMotion } from "../core/dom.js";

const POINTS = 560;
const TONES = {
  ok: [41, 224, 255],
  busy: [169, 139, 255],
  warn: [255, 181, 71],
  bad: [255, 77, 106],
};

function sphere(count) {
  const points = [];
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2, r = Math.sqrt(1 - y * y), theta = i * 2.39996;
    points.push([Math.cos(theta) * r, y, Math.sin(theta) * r]);
  }
  return points;
}

export class Orb {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.points = sphere(POINTS);
    this.tone = TONES.ok;
    this.raf = 0;
    this.frame = this.frame.bind(this);
  }

  setState(state) {
    this.tone = TONES[state] || TONES.ok;
    if (reducedMotion()) this.draw(0);
  }

  start() {
    cancelAnimationFrame(this.raf);
    if (reducedMotion()) { requestAnimationFrame(() => this.draw(0)); return; }
    this.raf = requestAnimationFrame(this.frame);
  }

  stop() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  frame(t) {
    if (!this.canvas.isConnected) { this.stop(); return; }
    this.draw(t);
    this.raf = requestAnimationFrame(this.frame);
  }

  draw(t) {
    const { canvas, ctx } = this;
    const dpr = Math.min(2, devicePixelRatio || 1), w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    if (canvas.width !== Math.round(w * dpr)) { canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const [r, g, b] = this.tone;
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.33 * (1 + Math.sin(t * 0.0016) * 0.035);
    const halo = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.55);
    halo.addColorStop(0, `rgba(${r},${g},${b},.28)`);
    halo.addColorStop(0.45, "rgba(80,120,255,.10)");
    halo.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.55, 0, Math.PI * 2); ctx.fill();
    const a = t * 0.00028, ca = Math.cos(a), sa = Math.sin(a), ct = Math.cos(0.42), st = Math.sin(0.42);
    for (const [x, y, z] of this.points) {
      const x1 = x * ca + z * sa, z1 = -x * sa + z * ca, y1 = y * ct - z1 * st, z2 = y * st + z1 * ct;
      const k = (z2 + 1) / 2, wave = 1 + Math.sin(y * 6 + t * 0.003) * 0.025, size = 0.6 + 1.5 * k;
      ctx.fillStyle = `rgba(${Math.round(r + (169 - r) * (1 - k))},${Math.round(g - 85 * (1 - k))},${b},${0.12 + 0.75 * k})`;
      ctx.fillRect(cx + x1 * R * wave - size / 2, cy + y1 * R * wave - size / 2, size, size);
    }
    ctx.lineWidth = 1;
    ctx.strokeStyle = `rgba(${r},${g},${b},.35)`;
    ctx.beginPath(); ctx.ellipse(cx, cy, R * 1.25, R * 0.32, Math.sin(t * 0.0004) * 0.3, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeStyle = "rgba(169,139,255,.28)";
    ctx.beginPath(); ctx.ellipse(cx, cy, R * 1.12, R * 0.22, -0.5 + Math.cos(t * 0.0003) * 0.2, 0, Math.PI * 2); ctx.stroke();
    const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 0.45);
    core.addColorStop(0, "rgba(220,250,255,.9)");
    core.addColorStop(0.3, `rgba(${r},${g},${b},.35)`);
    core.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.fillStyle = core;
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.45, 0, Math.PI * 2); ctx.fill();
  }
}
