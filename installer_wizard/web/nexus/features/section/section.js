import { h, mount } from "../../core/dom.js";
import { go } from "../../core/router.js";
import { classicFrame } from "../../components/classic-frame.js";
import { hasPanel, nativePanel } from "../../components/native-panel.js";
import { ZONES } from "../shell/zones.js";

export function sections() {
  return ZONES.flatMap((z) => (z.sections || []).filter(([tab]) => !tab.startsWith("f/")).map(([tab, label]) => ({ tab, label, zone: z })));
}

export const sectionHref = (tab) => (tab.startsWith("f/") ? `#/tool/${tab.slice(2)}` : tab === "features" ? "#/tools" : `#/section/${tab}`);

export function renderSection(outlet, route) {
  if (route.param === "features") { go("tools"); return; }
  if (route.param.startsWith("f/")) { go("tool", route.param.slice(2)); return; }
  const section = sections().find((s) => s.tab === route.param);
  if (!section) {
    mount(outlet, h("section", { class: "view" }, h("div", { class: "view-head" }, h("h2", {}, "Sezione non trovata"),
      h("a", { class: "btn", href: "#/home" }, "Torna alla Plancia"))));
    return;
  }
  document.title = `${section.label} · Atena Nexus`;
  mount(outlet, h("section", { class: "view" },
    h("a", { class: "back", href: `#/${section.zone.id}` }, "← ", section.zone.title),
    h("div", { class: "view-head" }, h("p", { class: "eyebrow" }, section.zone.title), h("h2", {}, section.label)),
    hasPanel(section.tab) ? nativePanel(section.tab) : classicFrame(section.tab, section.label)));
}
