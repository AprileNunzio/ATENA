import { h, mount } from "../../core/dom.js";
import { fail, toast } from "../../core/toast.js";
import { setMode } from "./mode.js";
import { saveSettings } from "./settings-form.js";

function initialAnswers(tool) {
  const answers = {};
  for (const step of tool.wizard) {
    if (step.kind === "mode") answers[step.id] = tool.mode;
    else if (step.setting && !(step.input === "password")) answers[step.id] = String(tool.values[step.setting] ?? "");
  }
  return answers;
}

function labelOf(step, value) {
  if (step.input === "password") return value ? "nuova chiave inserita" : "invariata";
  return step.options?.find((o) => o.value === value)?.label ?? (value || "—");
}

export function wizardPanel(tool, onDone) {
  const box = h("div", { class: "wizard" });
  const steps = tool.wizard;
  if (!steps.length) return h("p", { class: "dim" }, "Non c'è niente da configurare: questo strumento funziona da solo.");
  const answers = initialAnswers(tool);
  let index = 0;
  paint();
  return box;

  function stepper() {
    const total = steps.length + 1;
    return h("ol", { class: "wz-steps", "aria-label": "Passi della procedura" },
      Array.from({ length: total }, (_, i) => h("li", {
        class: i < index ? "done" : i === index ? "cur" : "", "aria-current": i === index ? "step" : null,
      }, h("span", { class: "sr-only" }, `Passo ${i + 1} di ${total}`))));
  }

  function choice(step) {
    return h("div", { class: "choices", role: "radiogroup", "aria-label": step.title }, step.options.map((o) => h("button", {
      type: "button", class: "choice", role: "radio", "aria-checked": String(answers[step.id] === o.value),
      "aria-pressed": String(answers[step.id] === o.value), onclick: () => { answers[step.id] = o.value; paint(); },
    }, h("b", {}, o.label), o.hint ? h("span", {}, o.hint) : null)));
  }

  function field(step) {
    const input = h("input", { class: "input", id: `wz-${step.id}`, type: step.input, placeholder: step.placeholder || "",
      value: answers[step.id] ?? "", autocomplete: step.input === "password" ? "new-password" : "off", maxlength: "500",
      oninput: (e) => { answers[step.id] = e.target.value; } });
    return h("div", { class: "field" }, h("label", { for: input.id }, "La tua risposta"), input);
  }

  function summary() {
    return h("div", { class: "wz-summary" }, steps.map((s) => h("div", {}, h("span", {}, s.title), h("b", {}, labelOf(s, answers[s.id])))));
  }

  function paint() {
    const last = index === steps.length;
    const step = steps[index];
    const nav = h("div", { class: "wz-nav" },
      index > 0 ? h("button", { class: "btn ghost", type: "button", onclick: () => { index--; paint(); } }, "Indietro") : null,
      h("span", { class: "spacer" }),
      last ? h("button", { class: "btn primary", type: "button", onclick: apply }, "Applica")
        : h("button", { class: "btn primary", type: "button", onclick: () => { index++; paint(); } }, "Avanti"));
    mount(box, stepper(),
      h("p", { class: "eyebrow" }, last ? "Riepilogo" : `Passo ${index + 1} di ${steps.length}`),
      h("h3", { class: "wz-title" }, last ? "Ecco cosa cambierà" : step.title),
      !last && step.text ? h("p", { class: "dim" }, step.text) : null,
      last ? summary() : step.kind === "field" ? field(step) : choice(step),
      nav);
    box.querySelector(".choice[aria-checked='true'], .input, .btn.primary")?.focus({ preventScroll: true });
  }

  async function apply(event) {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const modeStep = steps.find((s) => s.kind === "mode");
      if (modeStep && answers.mode !== tool.mode) await setMode(tool.id, answers.mode);
      const changes = {};
      for (const s of steps) {
        if (!s.setting) continue;
        const value = String(answers[s.id] ?? "").trim();
        if (s.input === "password" && !value) continue;
        if (value !== String(tool.values[s.setting] ?? "")) changes[s.setting] = value;
      }
      if (Object.keys(changes).length) await saveSettings(tool.id, changes);
      toast(`${tool.name}: configurazione applicata`);
      onDone();
    } catch (err) {
      fail(err);
      button.disabled = false;
    }
  }
}
