import { h, reducedMotion } from "../../core/dom.js";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function runBench(canvas, state, log) {
  canvas.reset();
  log.replaceChildren();
  const nodes = new Map(state.nodes.map((n) => [n.id, n]));
  let total = 0;
  for (let i = 0; i < state.estimate.length; i++) {
    const step = state.estimate[i], node = nodes.get(step.node);
    const algorithm = node.algorithms.find((a) => a.id === step.algorithm);
    canvas.mark(step.node, "active");
    await wait(reducedMotion() ? 40 : Math.min(1100, Math.max(220, step.seconds * 900)));
    canvas.mark(step.node, "done");
    total += step.seconds;
    log.append(h("li", {}, h("span", { class: "g", "aria-hidden": "true" }, node.glyph),
      h("span", {}, `${node.label} · ${algorithm?.name || "personalizzato"}`), h("span", { class: "t" }, `${step.seconds.toFixed(2)} s`)));
    const next = state.estimate[i + 1];
    if (next) await canvas.particle(step.node, next.node, 320);
  }
  log.append(h("li", { class: "end" }, h("span", { class: "g", "aria-hidden": "true" }, "✓"),
    h("span", {}, "Risposta pronta (stima)"), h("span", { class: "t" }, `${total.toFixed(2)} s`)));
  setTimeout(() => canvas.reset(), 2500);
}
