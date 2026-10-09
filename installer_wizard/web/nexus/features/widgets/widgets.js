import { h, mount } from "../../core/dom.js";
import { widgetLauncher } from "../../components/widget-launcher.js";

export function renderWidgets(outlet) {
  mount(outlet, h("section", { class: "view" },
    h("div", { class: "view-head" },
      h("p", { class: "eyebrow" }, "Richiamo rapido"),
      h("h2", {}, "Widget"),
      h("p", {}, "Tocca un widget per mostrarlo subito sul display: con i dati dal vivo quando ci sono, altrimenti con gli ultimi mostrati. Li trovi anche con Ctrl+K da qualsiasi pagina.")),
    h("div", { class: "panel" }, widgetLauncher({ search: true })),
    h("div", { class: "panel min-pilot" }, h("p", { class: "ptitle" }, "Priorità, posizioni e widget personalizzati"),
      h("div", { class: "chips" }, h("a", { class: "btn ghost", href: "#/tool/desktop" }, "Apri il desktop a widget")))));
}
