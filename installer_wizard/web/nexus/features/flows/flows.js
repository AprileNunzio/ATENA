import { h, mount } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { allows } from "../../core/level.js";
import { refresh } from "../../core/summary.js";
import { fail, toast } from "../../core/toast.js";
import { runBench } from "./bench.js";
import { FlowCanvas } from "./canvas.js";
import { askPassword } from "./confirm.js";
import { renderInspector } from "./inspector.js";

const SAVE_DELAY = 500;
const when = (seconds) => new Date(seconds * 1000).toLocaleString("it-IT", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function renderFlows(outlet) {
  const view = h("section", { class: "view" }, h("div", { class: "skeleton skeleton-block" }));
  mount(outlet, view);
  let state = null, selected = null, saveTimer = 0, running = false;
  const history = [];
  const canvas = new FlowCanvas({
    onSelect: (id) => { selected = selected === id ? null : id; paintCanvas(); paintInspector(); },
    onMove: (id, point) => { snapshot(); state.draft.positions[id] = [point.x, point.y]; scheduleSave(); },
  });
  const templates = h("div", { class: "tpl", role: "group", "aria-label": "Modelli pronti" });
  const inspector = h("aside", { class: "insp panel", "aria-live": "polite" });
  const log = h("ol", { class: "bench-log" });
  const versions = h("div", { class: "panel min-pilot" });
  const status = h("span", { class: "dim small flow-status", role: "status" });
  const publishBtn = h("button", { class: "btn primary", type: "button", onclick: publish }, "Pubblica");
  const benchBtn = h("button", { class: "btn primary", type: "button", onclick: bench }, "Prova il flusso");
  load();

  async function load() {
    try { state = await api("/api/flows/studio"); } catch (err) { mount(view, h("p", { class: "login-err" }, err.message)); return; }
    if (!view.isConnected) return;
    state.draft.positions = state.draft.positions || {};
    build();
  }

  const templateName = () => state.templates[state.draft.template]?.name || (state.draft.template === "custom" ? "Personalizzato" : "Bozza attuale");
  const dirty = () => Object.keys(state.pending).length > 0;

  function snapshot() {
    history.push(JSON.stringify({ picks: state.draft.picks, positions: state.draft.positions, template: state.draft.template }));
    if (history.length > 60) history.shift();
  }

  function scheduleSave() {
    clearTimeout(saveTimer);
    status.textContent = "Salvataggio della bozza…";
    saveTimer = setTimeout(async () => {
      try {
        const result = await api("/api/flows/draft", { method: "PUT", body: state.draft });
        Object.assign(state, { pending: result.pending, traits: result.traits, estimate: result.estimate });
        state.draft = { ...result.draft, positions: result.draft.positions || {} };
        status.textContent = dirty() ? "Bozza salvata, non ancora pubblicata" : "Uguale a ciò che usa Atena";
        paintTemplates(); paintInspector(); paintCanvas(); publishBtn.disabled = !dirty();
      } catch (err) { status.textContent = ""; fail(err); }
    }, SAVE_DELAY);
  }

  function choose(nodeId, algorithmId) {
    if (state.draft.picks[nodeId] === algorithmId) return;
    snapshot();
    state.draft.picks = { ...state.draft.picks, [nodeId]: algorithmId };
    state.draft.template = "custom";
    paintCanvas(); paintInspector(); paintTemplates(); scheduleSave();
  }

  function applyTemplate(id) {
    snapshot();
    state.draft.picks = { ...state.templates[id].picks };
    state.draft.template = id;
    selected = null;
    paintCanvas(); paintInspector(); paintTemplates(); scheduleSave();
    toast(`Modello «${state.templates[id].name}» nella bozza`, { undo });
  }

  function undo() {
    const previous = history.pop();
    if (!previous) { toast("Niente da annullare"); return; }
    Object.assign(state.draft, JSON.parse(previous));
    paintCanvas(); paintInspector(); paintTemplates(); scheduleSave();
  }

  async function publish() {
    const password = await askPassword({ title: "Pubblicare il nuovo modo di ragionare?",
      text: "Atena userà subito il flusso della bozza. Per sicurezza conferma la tua identità.", action: "Pubblica" });
    if (!password) return;
    publishBtn.disabled = true;
    try {
      const result = await api("/api/flows/publish", { method: "POST", body: { password } });
      toast(result.changed.length ? `Versione ${result.version.version} pubblicata` : `Versione ${result.version.version} salvata (nessun cambiamento)`);
      refresh().catch(() => {});
      await load();
    } catch (err) { fail(err); publishBtn.disabled = false; }
  }

  async function rollback(version) {
    const password = await askPassword({ title: `Tornare alla versione ${version}?`,
      text: "Atena riprende subito il modo di ragionare di quella versione.", action: "Ripristina" });
    if (!password) return;
    try {
      await api(`/api/flows/rollback/${version}`, { method: "POST", body: { password } });
      toast(`Ripristinata la versione ${version}`);
      await load();
    } catch (err) { fail(err); }
  }

  async function discard() {
    try { Object.assign(state, await api("/api/flows/draft", { method: "DELETE" })); state.draft.positions = state.draft.positions || {}; history.length = 0; selected = null; paintAll(); toast("Bozza scartata"); }
    catch (err) { fail(err); }
  }

  async function bench() {
    if (running) return;
    running = true; benchBtn.disabled = true;
    try { await runBench(canvas, state, log); } finally { running = false; benchBtn.disabled = false; }
  }

  function paintTemplates() {
    mount(templates, Object.entries(state.templates).map(([id, t]) => h("button", {
      type: "button", "aria-pressed": String(state.draft.template === id), onclick: () => applyTemplate(id),
    }, h("b", {}, t.name), h("span", {}, t.hint))));
  }

  function paintCanvas() {
    canvas.render({ nodes: state.nodes, edges: state.edges, picks: state.draft.picks, positions: state.draft.positions,
      selected, editable: allows("pilot"), current: state.current });
  }

  function paintInspector() { renderInspector(inspector, state, selected, templateName(), choose); }

  function paintVersions() {
    mount(versions, h("p", { class: "ptitle" }, "Versioni pubblicate"),
      state.versions.length ? h("ul", { class: "versions" }, state.versions.slice(0, 12).map((v) => h("li", {},
        h("b", {}, `v${v.version}`), h("span", { class: "dim" }, `${when(v.at)} · ${v.author} · ${v.note}`),
        h("span", { class: "dim small" }, v.changes.length ? `${v.changes.length} impostazioni cambiate` : "nessun cambiamento"),
        h("button", { class: "btn ghost", type: "button", onclick: () => rollback(v.version) }, "Ripristina"))))
        : h("p", { class: "dim" }, "Ancora nessuna versione: la prima pubblicazione creerà la versione 1."));
  }

  function paintAll() { paintTemplates(); paintCanvas(); paintInspector(); paintVersions(); publishBtn.disabled = !dirty(); status.textContent = dirty() ? "Bozza non ancora pubblicata" : ""; }

  function build() {
    mount(view,
      h("div", { class: "view-head" }, h("p", { class: "eyebrow" }, "Flow Studio · flusso principale"), h("h2", {}, "Come ragiona Atena"),
        h("p", {}, "Ogni nodo è un passo del ragionamento. Le modifiche restano in bozza finché non le pubblichi; puoi sempre tornare a una versione precedente.")),
      h("p", { class: "flow-hint only-explorer" }, "Tocca un modello qui sotto per cambiare il modo di pensare di Atena, provalo e poi premi «Pubblica»."),
      h("div", { class: "flow-bar" }, templates,
        h("div", { class: "flow-actions" },
          h("button", { class: "btn ghost min-pilot", type: "button", onclick: undo }, "Annulla"),
          h("button", { class: "btn ghost min-pilot", type: "button", onclick: () => { snapshot(); state.draft.positions = {}; paintCanvas(); scheduleSave(); } }, "Riordina"),
          h("button", { class: "btn ghost min-pilot", type: "button", onclick: discard }, "Scarta bozza"),
          publishBtn)),
      status,
      h("div", { class: "flow-main" }, h("div", { class: "canvas-wrap" }, canvas.el), inspector),
      h("div", { class: "panel bench" }, h("div", { class: "bench-head" },
        h("div", {}, h("p", { class: "ptitle" }, "Banco di prova"), h("p", { class: "dim small" }, "Simulazione con tempi stimati: nessuna azione reale viene eseguita.")),
        benchBtn), log),
      versions);
    paintAll();
  }
}
