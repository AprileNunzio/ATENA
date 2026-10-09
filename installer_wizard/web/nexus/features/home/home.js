import { h, mount } from "../../core/dom.js";
import { LEVELS, chooseLevel } from "../../core/level.js";
import { store } from "../../core/store.js";
import { fail } from "../../core/toast.js";
import { Orb } from "../../components/orb.js";

export function renderHome(outlet) {
  const canvas = h("canvas", { "aria-hidden": "true" });
  const { user, level } = store.get();
  mount(outlet, h("section", { class: "view" },
    h("div", { class: "home-hero" },
      h("div", { class: "orb-box home-orb" }, canvas),
      h("div", {},
        h("p", { class: "eyebrow" }, "Benvenuto nel Nexus"),
        h("h2", { class: "home-say" }, user ? `Ciao ${user}, sono Atena.` : "Ciao, sono Atena."),
        h("p", { class: "dim" }, "Questo è il nuovo pannello di controllo. Scegli quanto vuoi vedere: puoi cambiare livello in qualsiasi momento dall'interruttore in alto."))),
    h("div", { class: "level-cards" }, LEVELS.map((l) => h("button", {
      type: "button", class: "level-card", "aria-pressed": String(l.id === level),
      onclick: () => chooseLevel(l.id).then(() => renderHome(outlet)).catch(fail),
    }, h("b", {}, l.label), h("span", {}, l.hint))))));
  const orb = new Orb(canvas);
  orb.start();
}
