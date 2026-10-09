import { h, mount } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { refresh } from "../../core/summary.js";
import { fail, toast } from "../../core/toast.js";
import { ring } from "../../components/charts.js";
import { STEPS } from "./steps.js";

const mark = (step, status, note = "") => api("/api/nexus/awakening", { method: "PUT", body: { step, status, note } });

export function renderAwakening(outlet) {
  const view = h("section", { class: "view awakening" }, h("div", { class: "skeleton skeleton-block" }));
  mount(outlet, view);
  let state = null, index = 0, answers = {}, busy = false, primary = null, shown = -1;
  load();

  async function load(jumpTo) {
    try { state = await api("/api/nexus/awakening"); } catch (err) { fail(err); return; }
    if (!view.isConnected) return;
    const next = state.steps.findIndex((s) => !s.status);
    index = jumpTo ?? (next < 0 ? state.steps.length : next);
    answers = index < state.steps.length ? STEPS[state.steps[index].id].init(state.current) : {};
    paint();
  }

  const set = (patch, repaint = true) => {
    answers = { ...answers, ...patch };
    if (repaint) paint();
    else if (primary) primary.disabled = busy || !STEPS[state.steps[index].id].valid(answers, state.current);
  };

  function stepList() {
    return h("ol", { class: "aw-steps", "aria-label": "Passi del Risveglio" }, [...state.steps, { id: "done" }].map((s, i) => {
      const done = s.status === "done" || s.status === "skipped";
      return h("li", { class: `${done ? "done" : ""}${i === index ? " cur" : ""}`, "aria-current": i === index ? "step" : null },
        h("button", { type: "button", class: "aw-step", onclick: () => { if (s.id !== "done") load(i); else { index = state.steps.length; paint(); } } },
          h("span", { class: "n" }, done ? "✓" : String(i + 1)),
          h("span", { class: "lb" }, s.id === "done" ? "Pronta" : STEPS[s.id].label,
            s.note ? h("small", {}, s.note) : s.status === "skipped" ? h("small", {}, "saltato") : null)));
    }));
  }

  function finale() {
    const p = state.progress;
    return h("div", { class: "panel aw-card" },
      h("p", { class: "eyebrow" }, "Risveglio"),
      h("h2", {}, p.complete ? "Sono pronta." : "Ci siamo quasi."),
      h("div", { class: "ready" }, ring(p.percent, "Risveglio completato"),
        h("p", { class: "dim" }, p.complete ? "Abbiamo deciso tutto insieme. Puoi rifare il Risveglio quando vuoi."
          : `Mancano ${p.total - p.finished} passi: puoi completarli adesso o più tardi.`)),
      h("div", { class: "aw-summary" }, state.steps.map((s) => h("div", {}, h("span", {}, STEPS[s.id].label),
        h("b", {}, s.note || (s.status === "skipped" ? "Saltato" : "Da fare"))))),
      h("div", { class: "aw-nav" },
        h("button", { class: "btn ghost", type: "button", onclick: restart }, "Ricomincia"),
        h("span", { class: "spacer" }),
        p.complete ? null : h("button", { class: "btn", type: "button", onclick: () => load() }, "Completa i passi mancanti"),
        h("a", { class: "btn primary", href: "#/home" }, "Vai alla Plancia")));
  }

  function card() {
    const id = state.steps[index].id, step = STEPS[id];
    const ok = step.valid(answers, state.current);
    return h("div", { class: "panel aw-card" },
      h("p", { class: "eyebrow" }, `Passo ${index + 1} di ${state.steps.length}`),
      h("h2", {}, step.title), h("p", { class: "aw-lead" }, step.text),
      step.form(answers, set, state.current),
      h("div", { class: "aw-nav" },
        index > 0 ? h("button", { class: "btn ghost", type: "button", onclick: () => load(index - 1) }, "Indietro") : null,
        h("span", { class: "spacer" }),
        h("button", { class: "btn ghost", type: "button", disabled: busy || null, onclick: () => advance(id, null) }, "Salta"),
        primary = h("button", { class: "btn primary", type: "button", disabled: busy || !ok || null, onclick: () => advance(id, step) }, busy ? "Applico…" : "Avanti")));
  }

  function paint() {
    primary = null;
    const body = index >= state.steps.length ? finale() : card();
    if (shown !== index) { body.classList.add("aw-enter"); shown = index; }
    mount(view, h("div", { class: "aw-layout" }, stepList(), body));
    view.querySelector(".aw-card .input, .aw-card .choice[aria-checked='true'], .aw-card .btn.primary")?.focus({ preventScroll: true });
  }

  async function advance(id, step) {
    busy = true; paint();
    try {
      if (step) {
        const note = await step.apply(answers, state.current, state.profiles);
        await mark(id, "done", note || "");
      } else {
        await mark(id, "skipped");
      }
      refresh().catch(() => {});
      busy = false;
      await load();
    } catch (err) {
      busy = false; paint(); fail(err);
    }
  }

  async function restart() {
    try { await api("/api/nexus/awakening/reset", { method: "POST" }); toast("Risveglio ricominciato"); await load(0); } catch (err) { fail(err); }
  }
}
