import { h, mount } from "../../core/dom.js";
import { classicFrame } from "../../components/classic-frame.js";
import { ZONES } from "../shell/zones.js";

export function classicSections() {
  return ZONES.flatMap((z) => (z.classic || []).filter(([tab]) => !tab.startsWith("f/")).map(([tab, label]) => ({ tab, label, zone: z })));
}

export function renderClassic(outlet, route) {
  const section = classicSections().find((s) => s.tab === route.param);
  if (!section) {
    mount(outlet, h("section", { class: "view" }, h("div", { class: "view-head" }, h("h2", {}, "Sezione non trovata"),
      h("a", { class: "btn", href: "#/home" }, "Torna alla Plancia"))));
    return;
  }
  document.title = `${section.label} · Atena Nexus`;
  mount(outlet, h("section", { class: "view" },
    h("a", { class: "back", href: `#/${section.zone.id}` }, "← ", section.zone.title),
    h("div", { class: "view-head" }, h("p", { class: "eyebrow" }, section.zone.title), h("h2", {}, section.label)),
    classicFrame(section.tab, section.label)));
}
