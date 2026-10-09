import { h, mount } from "../core/dom.js";

const providers = new Set();
const LIMIT = 14;
let overlay = null, input = null, list = null, items = [], index = 0, opener = null;

export const addSource = (provider) => providers.add(provider);

function normalize(text) {
  return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

function score(item, words) {
  const title = normalize(item.title), haystack = `${title} ${normalize(item.keywords || "")}`;
  if (!words.every((w) => haystack.includes(w))) return 0;
  const phrase = words.join(" ");
  if (!phrase) return 1;
  if (title === phrase) return 5;
  if (title.startsWith(phrase)) return 4;
  if (title.split(/[\s·]+/).some((word) => word.startsWith(phrase))) return 3;
  return title.includes(phrase) ? 2 : 1;
}

function render() {
  const words = normalize(input.value.trim()).split(/\s+/).filter(Boolean);
  items = [...providers].flatMap((p) => p()).map((item, order) => ({ item, order, rank: score(item, words) }))
    .filter((x) => x.rank > 0).sort((a, b) => b.rank - a.rank || a.order - b.order).slice(0, LIMIT).map((x) => x.item);
  index = Math.min(index, Math.max(0, items.length - 1));
  if (!items.length) { mount(list, h("li", { class: "pal-empty" }, "Nessun risultato. Prova con un'altra parola.")); return; }
  mount(list, items.map((item, i) => h("li", {},
    h("button", { type: "button", role: "option", id: `pal-${i}`, "aria-selected": String(i === index), onclick: () => run(i) },
      h("span", { class: "g", "aria-hidden": "true" }, item.glyph || "›"), item.title, h("small", {}, item.kind)))));
  input.setAttribute("aria-activedescendant", `pal-${index}`);
}

function run(i) {
  const item = items[i];
  close();
  item?.run();
}

function onKey(event) {
  if (event.key === "ArrowDown") { event.preventDefault(); index = (index + 1) % Math.max(1, items.length); render(); }
  else if (event.key === "ArrowUp") { event.preventDefault(); index = (index - 1 + items.length) % Math.max(1, items.length); render(); }
  else if (event.key === "Enter") { event.preventDefault(); run(index); }
  else if (event.key === "Escape") { event.preventDefault(); close(); }
}

function build() {
  input = h("input", { class: "pal-input", placeholder: "Vai a… (es. firewall, telecamere, livello)", autocomplete: "off",
    spellcheck: "false", role: "combobox", "aria-expanded": "true", "aria-controls": "pal-list", "aria-label": "Cerca ovunque" });
  list = h("ul", { id: "pal-list", role: "listbox" });
  overlay = h("div", { class: "pal", hidden: true, onclick: (e) => { if (e.target === overlay) close(); } },
    h("div", { class: "pal-box", role: "dialog", "aria-modal": "true", "aria-label": "Cerca ovunque" }, input, list));
  input.addEventListener("input", () => { index = 0; render(); });
  input.addEventListener("keydown", onKey);
  document.body.append(overlay);
}

export function open() {
  if (!overlay) build();
  opener = document.activeElement;
  overlay.hidden = false;
  input.value = "";
  index = 0;
  render();
  input.focus();
}

export function close() {
  if (!overlay || overlay.hidden) return;
  overlay.hidden = true;
  opener?.focus?.();
}

export function installShortcut() {
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      overlay && !overlay.hidden ? close() : open();
    }
  });
}
