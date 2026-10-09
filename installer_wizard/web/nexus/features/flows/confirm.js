import { h } from "../../core/dom.js";

export function askPassword({ title, text, action }) {
  return new Promise((resolve) => {
    const input = h("input", { class: "input", id: "nx-confirm-pass", type: "password", autocomplete: "current-password", maxlength: "256", required: true });
    const close = (value) => { overlay.remove(); document.removeEventListener("keydown", onKey); resolve(value); };
    const onKey = (event) => { if (event.key === "Escape") close(null); };
    const overlay = h("div", { class: "pal", onclick: (event) => { if (event.target === overlay) close(null); } },
      h("form", { class: "confirm-box", role: "dialog", "aria-modal": "true", "aria-labelledby": "nx-confirm-title",
        onsubmit: (event) => { event.preventDefault(); if (input.value) close(input.value); } },
      h("h2", { id: "nx-confirm-title" }, title),
      h("p", { class: "dim" }, text),
      h("div", { class: "field" }, h("label", { for: input.id }, "La tua password di sistema"), input),
      h("div", { class: "aw-nav" },
        h("button", { class: "btn ghost", type: "button", onclick: () => close(null) }, "Annulla"),
        h("span", { class: "spacer" }),
        h("button", { class: "btn primary", type: "submit" }, action))));
    document.addEventListener("keydown", onKey);
    document.body.append(overlay);
    input.focus();
  });
}
