import { h } from "../core/dom.js";

const HASH = /^(f\/)?[a-z0-9][a-z0-9_-]{0,40}$/;
const MIN_HEIGHT = 520;

export function classicFrame(target, title) {
  if (!HASH.test(target)) return h("p", { class: "login-err" }, "Sezione non valida");
  const frame = h("iframe", { class: "classic-frame", src: `/?embed=1#${target}`, title, referrerpolicy: "no-referrer", loading: "lazy" });
  frame.addEventListener("load", () => {
    let doc;
    try { doc = frame.contentDocument; } catch { return; }
    if (!doc?.body) return;
    const fit = () => { frame.style.height = `${Math.max(MIN_HEIGHT, doc.documentElement.scrollHeight + 8)}px`; };
    fit();
    new ResizeObserver(fit).observe(doc.body);
  });
  return h("div", { class: "classic-box" },
    h("div", { class: "classic-bar" },
      h("span", { class: "dim small" }, "Tutte le opzioni di questa sezione, come nel pannello classico."),
      h("a", { class: "btn ghost", href: `/#${target}`, target: "_blank", rel: "noopener noreferrer" }, "Apri a schermo intero ↗")),
    frame);
}
