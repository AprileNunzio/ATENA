import { h, mount } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { allows } from "../../core/level.js";
import { store } from "../../core/store.js";
import { refresh } from "../../core/summary.js";
import { fail, toast } from "../../core/toast.js";
import { freshKey, statePill } from "../../components/tool-card.js";
import { freshBadge, markSeen } from "../../components/badge.js";
import { MODES, modeControl, setMode } from "./mode.js";
import { settingsForm } from "./settings-form.js";
import { wizardPanel } from "./wizard.js";
import { zone } from "../shell/zones.js";
import { classicFrame } from "../../components/classic-frame.js";

const TABS = [
  { id: "guide", label: "Configura con me", min: "explorer" },
  { id: "settings", label: "Impostazioni", min: "pilot" },
  { id: "full", label: "Pannello completo", min: "explorer" },
  { id: "advanced", label: "Avanzate", min: "architect" },
];

function initialTab(tool) {
  if (!allows("pilot")) return tool.wizard.length ? "guide" : "full";
  return tool.panel || !tool.settings.length ? "full" : "settings";
}

export async function toggleFavorite(fid) {
  const current = store.get().favorites;
  const favorites = current.includes(fid) ? current.filter((f) => f !== fid) : [...current, fid];
  const prefs = await api("/api/nexus/preferences", { method: "PUT", body: { favorites } });
  store.set({ favorites: prefs.favorites });
  return prefs.favorites.includes(fid);
}

function advanced(tool) {
  const data = { id: tool.id, zone: tool.zone, family: tool.family, level: tool.level, source: tool.source, mode: tool.mode,
    requires: tool.requires, hardware: tool.hardware, settings: Object.fromEntries(tool.settings.map((s) => [s.key, tool.values[s.key] ?? ""])) };
  return [
    h("pre", { class: "json" }, JSON.stringify(data, null, 2)),
    h("div", { class: "chips" }, h("a", { class: "btn ghost", href: `/classic#f/${encodeURIComponent(tool.id)}` }, "Scheda nel pannello classico ↗")),
  ];
}

function heroState(tool) {
  const pill = statePill(tool);
  const reason = tool.reason && tool.reason.trim() !== pill.textContent.trim() ? h("span", { class: "dim small" }, tool.reason) : null;
  return h("div", { class: "tool-hero-state" }, pill, freshBadge(tool), reason);
}

export function renderTool(outlet, route) {
  const fid = route.param;
  const view = h("section", { class: "view" }, h("div", { class: "skeleton skeleton-block" }));
  mount(outlet, view);
  let tab = null;
  load();

  async function load() {
    let tool;
    try {
      tool = await api(`/api/nexus/tools/${encodeURIComponent(fid)}`);
    } catch (err) {
      mount(view, h("div", { class: "view-head" }, h("h2", {}, "Strumento non trovato"), h("p", {}, err.message),
        h("a", { class: "btn", href: "#/tools" }, "Torna agli strumenti")));
      return;
    }
    if (!view.isConnected) return;
    document.title = `${tool.name} · Atena Nexus`;
    tab = tab || initialTab(tool);
    paint(tool);
    if (tool.badge) { markSeen(freshKey(tool)); refresh().catch(() => {}); }
  }

  async function changeMode(tool, mode) {
    const previous = tool.mode;
    try {
      await setMode(tool.id, mode);
      toast(`${tool.name}: ${MODES.find((m) => m.value === mode).label.toLowerCase()}`,
        { undo: () => setMode(tool.id, previous).then(after).catch(fail) });
      after();
    } catch (err) { fail(err); }
  }

  function after() {
    refresh().catch(() => {});
    load();
  }

  function paint(tool) {
    const favorite = store.get().favorites.includes(tool.id);
    const tabs = TABS.filter((t) => allows(t.min));
    if (!tabs.some((t) => t.id === tab)) tab = tabs[0].id;
    const body = tab === "guide" ? wizardPanel(tool, after) : tab === "settings" ? settingsForm(tool, after)
      : tab === "full" ? classicFrame(`f/${tool.id}`, `Pannello completo di ${tool.name}`) : advanced(tool);
    mount(view,
      h("a", { class: "back", href: `#/${tool.zone === "tools" ? `tools/${tool.family}` : tool.zone}` }, "← ", tool.family_label || zone(tool.zone)?.title || "Indietro"),
      h("header", { class: "tool-hero panel" },
        h("span", { class: "glyph big", "aria-hidden": "true" }, tool.icon),
        h("div", { class: "tool-hero-copy" },
          h("p", { class: "eyebrow" }, tool.family_label || zone(tool.zone)?.title || ""),
          h("h2", {}, tool.name),
          h("p", { class: "dim" }, tool.description),
          heroState(tool)),
        h("div", { class: "tool-hero-actions" },
          modeControl(tool, (mode) => changeMode(tool, mode)),
          h("button", { type: "button", class: `btn ghost fav${favorite ? " on" : ""}`, "aria-pressed": String(favorite),
            onclick: () => toggleFavorite(tool.id).then((on) => { toast(on ? "Aggiunto ai preferiti" : "Tolto dai preferiti"); paint(tool); }).catch(fail),
          }, favorite ? "★ Preferito" : "☆ Preferito"))),
      tool.capabilities.length ? h("details", { class: "caps-box" },
        h("summary", {}, `Cosa sa fare (${tool.capabilities.length})`),
        h("ul", { class: "caps" }, tool.capabilities.map((c) => h("li", {}, c)))) : null,
      h("div", { class: "seg tabs", role: "tablist", "aria-label": "Sezioni dello strumento" }, tabs.map((t) => h("button", {
        type: "button", role: "tab", "aria-selected": String(t.id === tab), "aria-pressed": String(t.id === tab),
        onclick: () => { tab = t.id; paint(tool); },
      }, t.label))),
      h("div", { class: `panel${tab === "full" ? " panel-flush" : ""}`, role: "tabpanel" }, body));
  }
}
