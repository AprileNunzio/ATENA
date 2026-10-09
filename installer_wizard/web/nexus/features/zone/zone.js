import { h, mount } from "../../core/dom.js";
import { zone } from "../shell/zones.js";

export function renderZone(outlet, route) {
  const z = zone(route.id);
  const links = (z.classic || []).map(([tab, label]) => h("a", { class: "btn ghost", href: `/#${tab}` }, label, " ↗"));
  mount(outlet, h("section", { class: "view" },
    h("div", { class: "view-head" }, h("p", { class: "eyebrow" }, "Zona in costruzione"), h("h2", {}, z.title), h("p", {}, z.lead)),
    h("div", { class: "panel" },
      h("p", { class: "ptitle" }, "Nel frattempo"),
      h("p", { class: "dim" }, "Questa zona del Nexus arriva in una delle prossime fasi. Puoi già usare le stesse funzioni nel pannello classico:"),
      links.length ? h("div", { class: "chips" }, links) : null)));
}
