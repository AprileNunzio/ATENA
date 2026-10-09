import { h, mount } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { fail } from "../../core/toast.js";
import { radar } from "../../components/charts.js";

function sources(state) {
  const list = [["draft", "Bozza", state.draft.picks], ["current", "In uso adesso", state.current]];
  for (const [id, t] of Object.entries(state.templates)) list.push([`tpl:${id}`, `Modello · ${t.name}`, t.picks]);
  for (const v of state.versions.slice(0, 10)) list.push([`v:${v.version}`, `Versione ${v.version}`, v.picks]);
  return list;
}

function picker(id, list, value, onChange) {
  return h("select", { class: "input", id, onchange: (e) => onChange(e.target.value) },
    list.map(([key, label]) => h("option", { value: key, selected: key === value ? true : null }, label)));
}

function total(estimate) {
  return estimate.reduce((sum, step) => sum + step.seconds, 0);
}

export function comparePanel(state) {
  const box = h("div", { class: "panel compare min-pilot" });
  const result = h("div", { class: "compare-result", "aria-live": "polite" });
  let left = "current", right = "draft";
  paint();
  return box;

  function paint() {
    const list = sources(state);
    mount(box,
      h("p", { class: "ptitle" }, "Confronto A/B"),
      h("div", { class: "compare-pick" },
        h("div", { class: "field" }, h("label", { for: "cmp-a" }, "Flusso A"), picker("cmp-a", list, left, (v) => { left = v; run(); })),
        h("div", { class: "field" }, h("label", { for: "cmp-b" }, "Flusso B"), picker("cmp-b", list, right, (v) => { right = v; run(); }))),
      result);
    run();
  }

  async function run() {
    const list = new Map(sources(state).map(([key, label, picks]) => [key, { label, picks }]));
    const a = list.get(left), b = list.get(right);
    try {
      const data = await api("/api/flows/compare", { method: "POST", body: { a: { picks: a.picks }, b: { picks: b.picks } } });
      const nodes = new Map(state.nodes.map((n) => [n.id, n]));
      const name = (nid, aid) => nodes.get(nid).algorithms.find((x) => x.id === aid)?.name || "personalizzato";
      const ta = total(data.a.estimate), tb = total(data.b.estimate), max = Math.max(ta, tb, 0.01);
      mount(result,
        h("div", { class: "compare-sides" },
          [[a.label, data.a, ta], [b.label, data.b, tb]].map(([label, side, seconds], i) => h("div", { class: `compare-side side-${i ? "b" : "a"}` },
            h("b", {}, label), radar(side.traits),
            h("div", { class: "compare-time" }, h("span", {}, `${seconds.toFixed(2)} s stimati`),
              h("i", { style: { width: `${(seconds / max) * 100}%` } }))))),
        data.different.length
          ? h("ul", { class: "compare-diff" }, data.different.map((nid) => h("li", {},
            h("span", { class: "dim" }, nodes.get(nid).label), h("span", { class: "side-a" }, name(nid, data.a.picks[nid])),
            h("span", { "aria-hidden": "true" }, "→"), h("span", { class: "side-b" }, name(nid, data.b.picks[nid])))))
          : h("p", { class: "dim" }, "I due flussi sono identici."));
    } catch (err) { fail(err); }
  }
}
