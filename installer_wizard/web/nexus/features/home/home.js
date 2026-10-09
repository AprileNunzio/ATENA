import { h, mount } from "../../core/dom.js";
import { go } from "../../core/router.js";
import { store } from "../../core/store.js";
import { onSummary, summary } from "../../core/summary.js";
import { ring } from "../../components/charts.js";
import { Orb } from "../../components/orb.js";
import { activityPanel, componentsPanel, freshPanel, statTiles, todoPanel } from "./panels.js";
import { trackSystem } from "./series.js";

const KID_TILES = [
  { glyph: "❝", title: "Parla con me", text: "Scrivimi o usa il microfono", route: ["tools", "communication"] },
  { glyph: "◐", title: "I miei sensi", text: "Occhi, orecchie e mani", route: ["tools", "perception"] },
  { glyph: "⌂", title: "La mia casa", text: "Luci, stanze e persone", route: ["tools", "home"] },
  { glyph: "⟁", title: "Come penso", text: "Scegli il mio modo di ragionare", route: ["flows"] },
];

trackSystem();

export function renderHome(outlet) {
  const canvas = h("canvas", { "aria-hidden": "true" });
  const sayExplorer = h("h2", { class: "home-say only-explorer" }, "Ciao! Sono Atena.");
  const sayPilot = h("h2", { class: "home-say min-pilot" }, "Caricamento dello stato…");
  const ringBox = h("div", { class: "ring-box" });
  const stats = h("div", { class: "stats min-pilot" });
  const todos = h("div", { class: "panel" });
  const activity = h("div", { class: "panel" });
  const components = h("div", { class: "panel min-architect" });
  const fresh = h("div", { class: "panel fresh-panel", hidden: true });
  const view = h("section", { class: "view" },
    h("div", { class: "home-hero" },
      h("div", { class: "orb-box home-orb" }, canvas),
      h("div", { class: "home-copy" },
        h("p", { class: "eyebrow" }, "Stato di Atena"), sayExplorer, sayPilot,
        h("div", { class: "ready" }, ringBox,
          h("div", { class: "ready-copy" },
            h("span", { class: "only-explorer" }, "Quanto sto bene"),
            h("span", { class: "min-pilot" }, "Salute dei componenti")),
          h("a", { class: "btn primary", href: "#/awakening" }, "Risveglio guidato")))),
    h("div", { class: "kid only-explorer" }, KID_TILES.map((t) => h("button", { type: "button", onclick: () => go(...t.route) },
      h("span", { class: "kg", "aria-hidden": "true" }, t.glyph), h("b", {}, t.title), h("span", {}, t.text)))),
    fresh,
    stats,
    h("div", { class: "cols min-pilot" }, todos, activity),
    components);
  mount(outlet, view);
  const orb = new Orb(canvas);
  orb.start();

  const paintSummary = (data) => {
    if (!data) return;
    orb.setState(data.tone);
    sayExplorer.textContent = data.headline.explorer;
    sayPilot.textContent = data.headline.pilot;
    mount(ringBox, ring(data.health, "Salute dei componenti"));
    mount(todos, todoPanel(data.todos));
    mount(components, componentsPanel(data.components));
    const freshContent = freshPanel(data.fresh);
    fresh.hidden = !freshContent;
    if (freshContent) mount(fresh, freshContent);
  };
  const paintSnapshot = (snapshot) => {
    mount(stats, statTiles(snapshot?.system));
    mount(activity, activityPanel(snapshot?.events));
  };
  paintSummary(summary());
  paintSnapshot(store.get().snapshot);
  const offSummary = onSummary((data) => { if (!view.isConnected) { offSummary(); return; } paintSummary(data); });
  const offStore = store.subscribe((state, changed) => {
    if (!view.isConnected) { offStore(); return; }
    if (changed.includes("snapshot")) paintSnapshot(state.snapshot);
  });
}
