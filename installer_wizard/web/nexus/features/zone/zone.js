import { h, mount } from "../../core/dom.js";
import { allows } from "../../core/level.js";
import { go } from "../../core/router.js";
import { onSummary, summary, toolsIn } from "../../core/summary.js";
import { toolCard } from "../../components/tool-card.js";
import { zone } from "../shell/zones.js";

function classicLinks(z) {
  const links = (z.classic || []).map(([tab, label]) => h("a", { class: "btn ghost", href: `/#${tab}` }, label, h("span", { "aria-hidden": "true" }, " ↗")));
  return links.length ? h("div", { class: "panel" }, h("p", { class: "ptitle" }, "Nel pannello classico"), h("div", { class: "chips" }, links)) : null;
}

function familyChips(families, active) {
  return h("div", { class: "chips", role: "group", "aria-label": "Famiglie di strumenti" },
    [["", "Tutte"], ...Object.entries(families)].map(([id, label]) => h("button", {
      type: "button", class: "chip", "aria-pressed": String(active === id), onclick: () => go("tools", id),
    }, label)));
}

function toolGroups(tools, families, family, query) {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const visible = tools.filter((t) => allows(t.level) && (!family || t.family === family)
    && words.every((w) => `${t.name} ${t.description}`.toLowerCase().includes(w)));
  if (!visible.length) return [h("p", { class: "dim" }, "Nessuno strumento trovato. Prova con un'altra parola o togli i filtri.")];
  const order = Object.keys(families);
  const groups = [...new Set(visible.map((t) => t.family || ""))].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return groups.flatMap((g) => [
    g ? h("h3", { class: "fam-h" }, families[g] || g) : null,
    h("div", { class: "tool-grid" }, visible.filter((t) => (t.family || "") === g).map(toolCard)),
  ]);
}

export function renderZone(outlet, route) {
  const z = zone(route.id);
  const list = h("div", { class: "tool-list", "aria-live": "polite" });
  const lead = h("p", {}, z.lead);
  const isTools = z.id === "tools";
  let query = "";
  const search = isTools ? h("input", { class: "input", type: "search", placeholder: "Cerca: webcam, luci, telegram…",
    "aria-label": "Cerca uno strumento", autocomplete: "off", oninput: (e) => { query = e.target.value; paint(summary()); } }) : null;
  const chips = h("div");
  const view = h("section", { class: "view" },
    h("div", { class: "view-head" }, h("p", { class: "eyebrow" }, z.group), h("h2", {}, z.title), lead),
    isTools ? h("div", { class: "toolbar" }, search) : null, chips, list, classicLinks(z));
  mount(outlet, view);

  function paint(data) {
    if (!data) { mount(list, h("div", { class: "skeleton skeleton-block" })); return; }
    const tools = toolsIn(z.id);
    if (isTools) {
      const visible = tools.filter((t) => allows(t.level));
      lead.textContent = `${visible.length} strumenti in ${Object.keys(data.families).length} famiglie, ${visible.filter((t) => t.enabled).length} attivi.`;
      mount(chips, familyChips(data.families, route.param));
    }
    if (!tools.length && !isTools) {
      mount(list, h("p", { class: "dim" }, "Le pagine di questa zona arrivano nelle prossime fasi del Nexus."));
      return;
    }
    mount(list, toolGroups(tools, data.families, isTools ? route.param : "", query));
  }
  paint(summary());
  const off = onSummary((data) => { if (!view.isConnected) { off(); return; } paint(data); });
}
