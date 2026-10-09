import { h } from "../core/dom.js";

const HASH = /^(f\/)?[a-z0-9][a-z0-9_-]{0,40}$/;
const MIN_HEIGHT = 480;
const GAP = 18;

function scroller(el) {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node);
    if (overflowY === "auto" || overflowY === "scroll") return node;
  }
  return null;
}

export function classicFrame(target, title) {
  if (!HASH.test(target)) return h("p", { class: "login-err" }, "Sezione non valida");
  const frame = h("iframe", { class: "classic-frame", src: `/classic?embed=1#${target}`, title, referrerpolicy: "no-referrer" });
  const veil = h("div", { class: "classic-veil", "aria-hidden": "true" }, h("span", { class: "classic-spin" }), h("span", {}, "Carico la sezione…"));
  const expand = h("button", { type: "button", class: "btn ghost", "aria-pressed": "false" }, "⤢ Espandi");
  const box = h("div", { class: "classic-box", "aria-busy": "true" },
    h("div", { class: "classic-bar" },
      h("span", { class: "classic-title" }, h("span", { class: "dot", "aria-hidden": "true" }), title),
      h("div", { class: "classic-tools" }, expand,
        h("a", { class: "btn ghost", href: `/classic#${target}`, target: "_blank", rel: "noopener noreferrer" }, "Nuova scheda ↗"))),
    h("div", { class: "classic-stage" }, frame, veil));

  const fit = () => {
    if (!box.isConnected) { stop(); return; }
    if (box.classList.contains("focus")) { frame.style.height = ""; return; }
    const area = scroller(box);
    const visible = area ? area.clientHeight : window.innerHeight;
    const bar = box.firstElementChild.offsetHeight;
    frame.style.height = `${Math.max(MIN_HEIGHT, Math.round(visible - bar - GAP * 2))}px`;
  };
  const onKey = (event) => { if (event.key === "Escape" && box.classList.contains("focus")) toggle(false); };
  const toggle = (on) => {
    box.classList.toggle("focus", on);
    document.body.classList.toggle("classic-focus", on);
    expand.setAttribute("aria-pressed", String(on));
    expand.textContent = on ? "⤡ Riduci" : "⤢ Espandi";
    fit();
    if (on) frame.focus();
  };
  const stop = () => {
    window.removeEventListener("resize", fit);
    window.removeEventListener("hashchange", stop);
    document.removeEventListener("keydown", onKey);
    document.body.classList.remove("classic-focus");
  };

  expand.addEventListener("click", () => toggle(!box.classList.contains("focus")));
  window.addEventListener("resize", fit, { passive: true });
  window.addEventListener("hashchange", stop);
  document.addEventListener("keydown", onKey);
  frame.addEventListener("load", () => {
    box.removeAttribute("aria-busy");
    box.classList.add("is-ready");
    try { frame.contentDocument?.addEventListener("keydown", onKey); } catch {}
  });
  requestAnimationFrame(fit);
  return box;
}
