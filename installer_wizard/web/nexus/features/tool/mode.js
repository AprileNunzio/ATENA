import { h } from "../../core/dom.js";
import { api } from "../../core/http.js";

export const MODES = [
  { value: "auto", label: "Automatico" },
  { value: "1", label: "Sempre attiva" },
  { value: "0", label: "Spenta" },
];

export const setMode = (fid, mode) => api(`/api/features/${encodeURIComponent(fid)}`, { method: "PUT", body: { mode } });

export function modeControl(tool, onChange) {
  if (!tool.toggle) return h("span", { class: "pill ok" }, "Sempre attiva");
  const seg = h("div", { class: "seg min-pilot", role: "radiogroup", "aria-label": `Modalità di ${tool.name}` },
    MODES.map((m) => h("button", {
      type: "button", role: "radio", "aria-checked": String(tool.mode === m.value), "aria-pressed": String(tool.mode === m.value),
      onclick: () => onChange(m.value),
    }, m.label)));
  const on = tool.mode !== "0";
  const toggle = h("button", {
    type: "button", class: "switch only-explorer", role: "switch", "aria-checked": String(on), "aria-label": `${tool.name}: ${on ? "accesa" : "spenta"}`,
    onclick: () => onChange(on ? "0" : "auto"),
  });
  return h("div", { class: "mode-ctl" }, seg, toggle);
}
