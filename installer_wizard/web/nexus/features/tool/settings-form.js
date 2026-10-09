import { h } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { fail, toast } from "../../core/toast.js";
import { fieldFor, readField } from "./fields.js";

export const saveSettings = (fid, values) =>
  api(`/api/features/${encodeURIComponent(fid)}/settings`, { method: "PUT", body: values });

export function settingsForm(tool, onSaved) {
  if (!tool.settings.length) return h("p", { class: "dim" }, "Questo strumento non ha impostazioni: funziona da solo.");
  const inputs = new Map();
  const rows = tool.settings.map((s, i) => {
    const id = `nx-set-${i}`;
    const input = fieldFor(s, tool.values[s.key], id);
    inputs.set(s.key, input);
    return h("div", { class: "field" },
      h("label", { for: id }, s.label),
      input,
      s.help ? h("small", { class: "dim" }, s.help) : null);
  });
  const submit = h("button", { class: "btn primary", type: "submit" }, "Salva e applica");
  return h("form", { class: "settings-form", onsubmit: send }, h("div", { class: "form-grid" }, rows), h("div", { class: "form-actions" }, submit));

  async function send(event) {
    event.preventDefault();
    const changes = {};
    try {
      for (const s of tool.settings) {
        const value = readField(s, inputs.get(s.key));
        if (value !== undefined && value !== String(tool.values[s.key] ?? "")) changes[s.key] = value;
      }
    } catch (err) { fail(err); return; }
    if (!Object.keys(changes).length) { toast("Nessuna modifica da salvare"); return; }
    submit.disabled = true;
    try {
      const result = await saveSettings(tool.id, changes);
      toast(result.applying?.length ? "Salvato: applico le modifiche…" : "Impostazioni salvate");
      onSaved();
    } catch (err) {
      fail(err);
    } finally {
      submit.disabled = false;
    }
  }
}
