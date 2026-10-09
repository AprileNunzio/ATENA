import { h } from "../core/dom.js";

const MODE = { auto: "Automatico", 1: "Sempre attivo", 0: "Spento" };

export const classicHref = (tool) => `/#f/${encodeURIComponent(tool.id)}`;

export function statePill(tool) {
  if (tool.fixed) return h("span", { class: "pill ok" }, "Sempre attiva");
  if (tool.risk) return h("span", { class: "pill warn" }, "Attiva a rischio");
  if (!tool.enabled) return h("span", { class: "pill" }, tool.mode === "0" ? "Spento" : "In attesa");
  return h("span", { class: `pill ${tool.mode === "auto" ? "info" : "ok"}` }, MODE[tool.mode] || "Attiva");
}

export function toolCard(tool) {
  const levelClass = tool.level === "architect" ? " min-architect" : tool.level === "pilot" ? " min-pilot" : "";
  return h("article", { class: `tool${levelClass}`, dataset: { on: String(tool.enabled) } },
    h("div", { class: "tool-head" },
      h("span", { class: "glyph", "aria-hidden": "true" }, tool.icon || "◆"),
      h("div", { class: "tool-id" }, h("h3", {}, tool.name), statePill(tool))),
    h("p", { class: "tool-desc" }, tool.description),
    !tool.enabled && tool.reason ? h("p", { class: "tool-why" }, tool.reason) : null,
    h("div", { class: "tool-foot" }, h("a", { class: "btn ghost", href: classicHref(tool) }, "Apri", h("span", { "aria-hidden": "true" }, " ↗"))));
}
