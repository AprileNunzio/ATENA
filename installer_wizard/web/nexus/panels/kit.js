import { h, mount } from "../core/dom.js";
import { api } from "../core/http.js";
import { store } from "../core/store.js";
import { fail, toast } from "../core/toast.js";

const locale = () => document.documentElement.lang || "it";

export { api, h, mount, toast, fail };

export const fmt = {
  num: (value, digits = 0) => Number(value ?? 0).toLocaleString(locale(), { maximumFractionDigits: digits }),
  bytes(value) {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let n = Number(value) || 0, i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
    return `${n.toLocaleString(locale(), { maximumFractionDigits: i ? 1 : 0 })} ${units[i]}`;
  },
  rate: (value) => `${fmt.bytes(value)}/s`,
  duration(seconds) {
    const s = Math.max(0, Math.round(Number(seconds) || 0));
    const d = Math.floor(s / 86400), hr = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return d ? `${d} g ${hr} h` : hr ? `${hr} h ${m} min` : m ? `${m} min` : `${s} s`;
  },
  when(value) {
    if (!value) return "—";
    const date = typeof value === "number" ? new Date(value < 1e12 ? value * 1000 : value) : new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(locale(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  },
  short: (text, n = 10) => (text ? String(text).slice(0, n) : "—"),
};

export const pill = (text, tone = "") => h("span", { class: `pill ${tone}`.trim() }, text);
export const note = (...kids) => h("p", { class: "np-note" }, ...kids);
export const mono = (text) => h("span", { class: "mono" }, text ?? "—");
export const row = (...kids) => h("div", { class: "np-row" }, ...kids);
export const grid = (...kids) => h("div", { class: "np-grid" }, ...kids);
export const spacer = () => h("span", { class: "np-spacer" });
export const tag = (text) => h("span", { class: "np-tag" }, text);
export const dots = (...parts) => h("span", { class: "np-dots" }, parts.filter((p) => p != null && p !== false && p !== "").map((p) => h("span", {}, p)));

export function section(title, ...kids) {
  return h("section", { class: "panel np-sec" }, title ? h("p", { class: "ptitle" }, title) : null, ...kids);
}

export function kv(rows) {
  return h("div", { class: "tbl-wrap" }, h("table", { class: "np-kv" }, h("tbody", {},
    rows.filter(Boolean).map(([label, value]) => h("tr", {}, h("th", { scope: "row" }, label), h("td", {}, value ?? "—"))))));
}

export function table(headers, rows, empty = "Niente da mostrare.") {
  if (!rows.length) return h("p", { class: "dim" }, empty);
  return h("div", { class: "tbl-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, headers.map((label) => h("th", {}, label)))),
    h("tbody", {}, rows.map((cells) => h("tr", {}, cells.map((cell) => h("td", {}, cell)))))));
}

export function bar(percent, tone = "") {
  const fill = h("i", {});
  Object.assign(fill.style, { width: `${Math.max(0, Math.min(100, Number(percent) || 0))}%` });
  return h("div", { class: `np-bar ${tone}`.trim(), role: "progressbar", "aria-valuenow": String(Math.round(percent || 0)), "aria-valuemin": "0", "aria-valuemax": "100" }, fill);
}

export function ask({ title, text = "", action = "Conferma", danger = false }) {
  return new Promise((resolve) => {
    const close = (value) => { overlay.remove(); document.removeEventListener("keydown", onKey); resolve(value); };
    const onKey = (event) => { if (event.key === "Escape") close(false); };
    const ok = h("button", { class: `btn ${danger ? "danger" : "primary"}`, type: "button", onclick: () => close(true) }, action);
    const overlay = h("div", { class: "pal", onclick: (event) => { if (event.target === overlay) close(false); } },
      h("div", { class: "confirm-box", role: "alertdialog", "aria-modal": "true", "aria-labelledby": "np-ask-title" },
        h("h2", { id: "np-ask-title" }, title),
        text ? h("p", { class: "dim" }, text) : null,
        h("div", { class: "aw-nav" },
          h("button", { class: "btn ghost", type: "button", onclick: () => close(false) }, "Annulla"),
          h("span", { class: "spacer" }), ok)));
    document.addEventListener("keydown", onKey);
    document.body.append(overlay);
    ok.focus();
  });
}

export function button(label, run, { kind = "", confirm = null, title = null, disabled = false } = {}) {
  const el = h("button", { type: "button", class: `btn ${kind}`.trim(), title, disabled });
  el.append(label);
  el.addEventListener("click", async () => {
    if (confirm && !(await ask(typeof confirm === "string" ? { title: confirm, danger: kind === "danger" } : confirm))) return;
    el.disabled = true;
    el.setAttribute("aria-busy", "true");
    try { await run(el); } catch (err) { fail(err); } finally { el.disabled = false; el.removeAttribute("aria-busy"); }
  });
  return el;
}

export function actions(...buttons) {
  return h("div", { class: "np-actions" }, ...buttons);
}

export async function copy(text, label = "Copiato negli appunti") {
  try { await navigator.clipboard.writeText(String(text)); toast(label); } catch { toast("Copia non riuscita: seleziona il testo a mano", { error: true }); }
}

export const copyButton = (text) => button("Copia", () => copy(text), { kind: "ghost sm" });

export function seg(options, value, onChange, label) {
  const group = h("div", { class: "seg", role: "radiogroup", "aria-label": label });
  const paint = (current) => mount(group, options.map(([id, text]) => h("button", {
    type: "button", role: "radio", "aria-checked": String(id === current), "aria-pressed": String(id === current),
    onclick: () => { paint(id); onChange(id); },
  }, text)));
  paint(value);
  return group;
}

export function select(options, value, onChange, label) {
  const el = h("select", { class: "input np-select", "aria-label": label, onchange: () => onChange(el.value) },
    options.map(([id, text]) => h("option", { value: id, selected: id === value }, text)));
  return el;
}

export function input({ label, value = "", type = "text", placeholder = "", name, secret = false, ...rest }) {
  const id = `np-${name || Math.random().toString(36).slice(2)}`;
  const el = h("input", { class: "input", id, name, type: secret ? "password" : type, value: value ?? "", placeholder, autocomplete: "off", spellcheck: "false", ...rest });
  return { el, field: h("div", { class: "field" }, h("label", { for: id }, label), el) };
}

export function toggle(label, checked, onChange) {
  const el = h("input", { type: "checkbox", class: "np-check", checked, onchange: () => onChange(el.checked) });
  return h("label", { class: "np-toggle" }, el, h("span", {}, label));
}

export function alive(node, stop) {
  const timer = setInterval(() => { if (!node.isConnected) { clearInterval(timer); stop(); } }, 2000);
}

export function live(node, run, ms = 5000) {
  let busy = false;
  const tick = async () => {
    if (busy || document.hidden) return;
    busy = true;
    try { await run(); } catch (err) { console.warn("Aggiornamento non riuscito", err); } finally { busy = false; }
  };
  tick();
  const timer = setInterval(() => { if (!node.isConnected) clearInterval(timer); else tick(); }, ms);
  return tick;
}

export function onSnapshot(node, render) {
  const state = store.get().snapshot;
  if (state) render(state);
  const off = store.subscribe((next, changed) => {
    if (!node.isConnected) { off(); return; }
    if (changed.includes("snapshot") && next.snapshot) render(next.snapshot);
  });
}

export function loading() {
  return h("div", { class: "np-loading" }, h("div", { class: "skeleton skeleton-block" }));
}

export function failure(err, retry) {
  return h("div", { class: "panel np-error", role: "alert" },
    h("p", {}, err?.message || String(err)),
    retry ? h("button", { class: "btn", type: "button", onclick: retry }, "Riprova") : null);
}

export async function upload(path, file, { accept = null, max = 0 } = {}) {
  if (accept && !accept.test(file.name)) throw new Error("Tipo di file non consentito");
  if (max && file.size > max) throw new Error("File troppo grande");
  if (!path.startsWith("/api/")) throw new Error("Percorso non consentito");
  const response = await fetch(path, { method: "POST", body: file, credentials: "same-origin", cache: "no-store", redirect: "error",
    headers: { "X-Atena-Request": "1", "Content-Type": "application/octet-stream" } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Errore ${response.status}`);
  return data;
}

export function filePick(label, accept, onFile) {
  const el = h("input", { type: "file", accept, class: "sr-only", onchange: () => { const f = el.files[0]; el.value = ""; if (f) onFile(f); } });
  return h("label", { class: "btn ghost" }, label, el);
}
