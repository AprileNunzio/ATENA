import { api, button, tag, fmt, h, input, live, mount, note, pill, row, section, seg, table, toast } from "../kit.js";

const STATE = { installed: ["installato", "ok"], installing: ["in installazione", "info"], queued: ["in coda", "warn"], failed: ["errore", "bad"], available: ["su richiesta", ""], removed: ["rimosso", ""] };
const NOTE = {
  local: "I modelli girano su questo computer con Ollama: tutto resta in casa.",
  remote: "Uso Ollama di un altro computer della rete: qui non installo nulla del cervello.",
  cloud: "Le risposte arrivano dal servizio cloud configurato nello strumento Cloud.",
  pending: "Il cervello non è ancora scelto: scegli dove deve pensare Atena.",
};
const MODES = [["local", "Su questo computer"], ["remote", "Su un altro computer"], ["cloud", "Nel cloud"]];

export default function packages(root) {
  const brainBox = h("div", { class: "np-sec" });
  const list = h("div");
  let mode = null, pick = "local";
  const url = input({ label: "Indirizzo del computer con Ollama", name: "brain-url", placeholder: "192.168.1.20" });

  function paintBrain() {
    const remote = pick === "remote";
    mount(brainBox,
      row(seg(MODES, pick, (v) => { pick = v; paintBrain(); }, "Dove pensa Atena"),
        pick !== mode || remote ? button("Applica", async () => {
          const body = { mode: pick, ...(remote ? { url: url.el.value.trim() } : {}) };
          await api("/api/packages/brain", { method: "POST", body });
          toast("Scelta salvata, applicazione in corso");
          await load();
        }, { kind: "primary sm", confirm: pick !== mode ? { title: "Cambiare dove pensa Atena?", text: "I componenti necessari si installano in background.", action: "Cambia" } : null }) : null),
      remote ? url.field : null,
      note(NOTE[mode] || ""));
  }

  async function load() {
    const d = await api("/api/packages");
    if (mode !== d.brain) { mode = d.brain; pick = mode === "pending" ? "local" : mode; paintBrain(); }
    mount(list, table(["Pacchetto", "Dimensione", "Stato", ""], d.packages.map((p) => {
      const [label, tone] = STATE[p.state] || [p.state, ""];
      const toggle = (on) => api(`/api/packages/${encodeURIComponent(p.id)}`, { method: "POST", body: { on } })
        .then(() => { toast(on ? "Installazione avviata in background" : "Pacchetto disattivato"); return load(); });
      const action = p.state === "installing" ? "" : !p.wanted ? button("Installa", () => toggle(true), { kind: "primary sm" })
        : p.removable ? button("Rimuovi", () => toggle(false), { kind: "ghost sm", confirm: { title: "Rimuovere il pacchetto?", text: "Lo puoi reinstallare quando vuoi.", action: "Rimuovi" } }) : "";
      return [h("div", {}, p.title, h("div", { class: "dim small" }, p.description, p.detected ? tag("dispositivo rilevato") : null, p.heavy ? tag("pesante per questo computer") : null)),
        h("span", { class: "mono" }, `${fmt.num(p.size_gb, 1)} GB`), pill(label, tone), h("div", { class: "cell-actions" }, action)];
    })));
  }

  mount(root,
    section("Cervello", brainBox),
    section("Pacchetti", list, note("Atena installa solo quello che usi. Puoi aggiungere un pacchetto da qui oppure chiederlo a voce, ad esempio «installa i documenti Office».")));
  live(root, load, 5000);
}
