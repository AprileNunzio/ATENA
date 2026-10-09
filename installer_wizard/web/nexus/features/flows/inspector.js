import { h } from "../../core/dom.js";
import { allows } from "../../core/level.js";
import { radar } from "../../components/charts.js";

const METERS = [["speed", "Velocità"], ["quality", "Qualità"], ["privacy", "Privacy"], ["saving", "Risparmio"]];

function legend(a, b) {
  return h("div", { class: "legend" }, h("span", {}, h("i", {}), a), b ? h("span", {}, h("i", { class: "cmp" }), b) : null);
}

function overview(state, templateName) {
  const t = state.traits.draft;
  return [
    h("p", { class: "ptitle" }, "Profilo del flusso"),
    h("h3", { class: "insp-title" }, templateName),
    radar(t, state.traits.default),
    legend("Bozza", "Predefinito"),
    h("div", { class: "meters" }, METERS.map(([key, label]) => h("div", { class: "meter" },
      h("span", {}, label), h("b", {}, `${t[key].toFixed(1)} / 5`), h("i", { style: { width: `${t[key] * 20}%` } })))),
    h("p", { class: "dim" }, allows("pilot") ? "Tocca un nodo per cambiare il suo algoritmo; trascina i nodi per riordinare il diagramma."
      : "Scegli un modello pronto qui sopra, poi provalo nel banco di prova."),
  ];
}

function pending(state) {
  const keys = Object.entries(state.pending);
  return h("div", { class: "min-architect" },
    h("p", { class: "ptitle" }, "Cosa cambierà pubblicando"),
    keys.length ? h("pre", { class: "json" }, JSON.stringify(state.pending, null, 2)) : h("p", { class: "dim" }, "Nessuna modifica: la bozza è uguale a ciò che usa Atena."));
}

function nodeDetail(node, state, choose) {
  const pick = state.draft.picks[node.id], live = state.current[node.id];
  const chosen = node.algorithms.find((a) => a.id === pick);
  const fallback = node.algorithms.find((a) => a.default);
  const canEdit = allows("pilot") && node.editable && !node.locked;
  return [
    h("p", { class: "ptitle" }, node.locked ? "Nodo protetto" : node.editable ? "Nodo" : "Nodo fisso"),
    h("h3", { class: "insp-title" }, h("span", { class: "insp-glyph", "aria-hidden": "true" }, node.glyph), node.label),
    h("p", { class: "dim" }, node.description),
    pick === "" ? h("p", { class: "aw-note" }, "Configurato a mano nel pannello Cervello: scegli un algoritmo per gestirlo da qui.") : null,
    h("div", { class: "algs", role: "radiogroup", "aria-label": `Algoritmo di ${node.label}` }, node.algorithms.map((a) => h("button", {
      type: "button", class: "alg", role: "radio", "aria-checked": String(a.id === pick), disabled: !canEdit || !a.available ? true : null,
      onclick: () => choose(node.id, a.id),
    },
    h("span", { class: "rd", "aria-hidden": "true" }),
    h("span", { class: "alg-copy" },
      h("b", {}, a.name),
      a.default ? h("span", { class: "tag" }, "predefinito") : null,
      a.id === live ? h("span", { class: "tag live" }, "in uso") : null,
      !a.available ? h("span", { class: "tag soon" }, "in arrivo") : null,
      h("small", {}, a.description))))),
    chosen ? radar(chosen.traits, fallback && fallback !== chosen ? fallback.traits : null) : null,
    chosen && fallback && fallback !== chosen ? legend(chosen.name, fallback.name) : null,
  ];
}

export function renderInspector(box, state, selected, templateName, choose) {
  const node = selected && state.nodes.find((n) => n.id === selected);
  box.replaceChildren(...[node ? nodeDetail(node, state, choose) : overview(state, templateName), pending(state)].flat().filter(Boolean));
}
