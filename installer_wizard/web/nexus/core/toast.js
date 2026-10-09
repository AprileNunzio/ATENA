import { h } from "./dom.js";

let current = null;
let timer = 0;

export function toast(message, { undo, error = false, seconds = 6 } = {}) {
  current?.remove();
  clearTimeout(timer);
  const close = () => { node.remove(); if (current === node) current = null; };
  const node = h("div", { class: `toast${error ? " error" : ""}`, role: error ? "alert" : "status" },
    h("span", {}, message),
    undo ? h("button", { type: "button", onclick: () => { close(); undo(); } }, "Annulla") : null);
  document.body.append(node);
  current = node;
  timer = setTimeout(close, seconds * 1000);
}

export const fail = (err) => toast(err?.message || String(err), { error: true });
