import { h, mount } from "../core/dom.js";
import { fail } from "../core/toast.js";
import { recall, widgets } from "../core/widgets.js";

function tile(widget) {
  return h("button", { type: "button", class: "wl-tile", title: widget.description || widget.name,
    onclick: (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      recall(widget).catch(fail).finally(() => { button.disabled = false; });
    } },
  h("span", { class: "wl-icon", "aria-hidden": "true" }, widget.icon || "▣"),
  h("span", { class: "wl-name" }, widget.name));
}

export function widgetLauncher({ limit = 0, search = false } = {}) {
  const grid = h("div", { class: "wl-grid", role: "group", "aria-label": "Widget da mostrare sul display" },
    h("div", { class: "skeleton wl-skeleton" }));
  let all = [], query = "";
  const paint = () => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    const shown = all.filter((w) => words.every((q) => `${w.name} ${w.description || ""} ${w.id}`.toLowerCase().includes(q)));
    mount(grid, shown.length ? (limit ? shown.slice(0, limit) : shown).map(tile) : h("p", { class: "dim" }, "Nessun widget trovato."));
  };
  widgets().then((list) => { all = list; paint(); }).catch((err) => mount(grid, h("p", { class: "login-err" }, err.message)));
  if (!search) return grid;
  const input = h("input", { class: "input", type: "search", placeholder: "Cerca un widget: meteo, musica, telecamera…",
    "aria-label": "Cerca un widget", autocomplete: "off", oninput: (e) => { query = e.target.value; paint(); } });
  return h("div", { class: "wl-box" }, input, grid);
}
