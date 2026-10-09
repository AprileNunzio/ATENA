import { api, h, input, kv, mono, mount, note, section, toast } from "../kit.js";

export default function config(root) {
  const fields = h("div", { class: "np-form" });
  const system = h("div");
  const save = h("button", { class: "btn primary", type: "submit" }, "Salva e applica");
  const form = h("form", { class: "np-sec", onsubmit: submit }, fields, h("div", { class: "np-actions" }, save));
  let initial = {};

  async function load() {
    const d = await api("/api/config");
    initial = Object.fromEntries(d.editable.map((f) => [f.key, f.value ?? ""]));
    mount(fields, d.editable.map((f) => input({ label: f.label, value: f.value, name: f.key, secret: f.secret, placeholder: f.secret ? "non impostata" : "" }).field));
    mount(system, kv(Object.entries(d.system).map(([k, v]) => [h("span", { class: "mono" }, k), mono(v || "—")])));
  }

  async function submit(event) {
    event.preventDefault();
    const body = {};
    new FormData(form).forEach((value, key) => { if (value !== initial[key]) body[key] = value; });
    if (!Object.keys(body).length) { toast("Nessuna modifica"); return; }
    save.disabled = true;
    try {
      const r = await api("/api/config", { method: "PUT", body });
      toast(r.changed.length ? `Salvato: ${r.changed.join(", ")}${r.applying.length ? " — applicazione in corso" : ""}` : "Nessuna modifica");
      await load();
    } catch (err) { toast(err.message, { error: true }); } finally { save.disabled = false; }
  }

  mount(root,
    section("Impostazioni", form, note("Le modifiche vengono salvate in /etc/atena/atena.env e applicate automaticamente, riavviando solo i componenti interessati.")),
    section("Parametri rilevati dal sistema", system));
  load().catch((err) => toast(err.message, { error: true }));
}
