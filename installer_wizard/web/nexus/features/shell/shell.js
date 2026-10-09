import { h, mount } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { LEVELS, allows, chooseLevel } from "../../core/level.js";
import { go } from "../../core/router.js";
import { store } from "../../core/store.js";
import { fail, toast } from "../../core/toast.js";
import { onSummary, summary } from "../../core/summary.js";
import { open as openPalette } from "../../components/palette.js";
import { countBadge, freshBadge, isSeen, markSeen } from "../../components/badge.js";
import { unseenFresh } from "../../components/tool-card.js";
import { GROUPS, ZONES, zone } from "./zones.js";

export function createShell(root) {
  const nav = h("nav", { class: "nav", "aria-label": "Zone del pannello" });
  const title = h("h1", { id: "nx-title" });
  const linkDot = h("span", { class: "link-state", role: "img", "aria-label": "Collegato ad Atena" });
  const levelSeg = h("div", { class: "seg", role: "group", "aria-label": "Livello di esperienza" });
  const outlet = h("main", { class: "outlet", id: "nx-outlet", tabindex: "-1" });
  const top = h("header", { class: "top" }, title, linkDot,
    h("button", { class: "search", type: "button", onclick: openPalette, "aria-label": "Cerca ovunque" },
      h("span", {}, "Cerca pagine, strumenti, azioni…"), h("kbd", {}, "Ctrl K")),
    levelSeg);
  mount(root, h("div", { class: "app" }, nav, h("div", { class: "main" }, top, outlet)));

  function renderLevels() {
    const { level } = store.get();
    mount(levelSeg, LEVELS.map((l) => h("button", {
      type: "button", "aria-pressed": String(l.id === level), title: l.hint,
      onclick: () => chooseLevel(l.id).then(() => toast(`Livello ${l.label}`)).catch(fail),
    }, l.label)));
  }

  function zoneMarker(z) {
    const fresh = (summary()?.tools || []).filter((t) => t.zone === z.id && allows(t.level) && unseenFresh(t)).length;
    if (fresh) return countBadge(fresh, `${fresh} novità o aggiornamenti`);
    return z.added && !isSeen(`zone:${z.id}:${z.added}`) && Date.now() - Date.parse(z.added) < 14 * 86400000
      ? freshBadge({ badge: "new", since: Date.parse(z.added) / 1000 }) : null;
  }

  function favoriteLinks() {
    const { favorites } = store.get();
    const tools = (summary()?.tools || []).filter((t) => favorites.includes(t.id));
    if (!tools.length) return [];
    return [h("div", { class: "navsec" }, "Preferiti"), ...tools.map((t) => h("a", { class: "nv nv-fav", href: `#/tool/${encodeURIComponent(t.id)}` },
      h("span", { class: "g", "aria-hidden": "true" }, t.icon), h("span", { class: "lb" }, t.name)))];
  }

  function renderNav() {
    const { route, user } = store.get();
    const sections = GROUPS.flatMap((group) => {
      const items = ZONES.filter((z) => z.group === group && allows(z.min));
      if (!items.length) return [];
      return [h("div", { class: "navsec" }, group), ...items.map((z) => h("a", {
        class: `nv${z.accent ? " accent" : ""}`, href: `#/${z.id}`, "aria-current": z.id === route ? "page" : null,
      }, h("span", { class: "g", "aria-hidden": "true" }, z.glyph), h("span", { class: "lb" }, z.title), zoneMarker(z)))];
    });
    mount(nav,
      h("a", { class: "brand", href: "#/home" }, "A.T.E.N.A.", h("small", {}, "NEXUS · 8080")),
      sections,
      favoriteLinks(),
      h("div", { class: "nav-foot" },
        h("a", { class: "nv", href: "/" }, h("span", { class: "g", "aria-hidden": "true" }, "▤"), h("span", { class: "lb" }, "Pannello classico")),
        h("button", { class: "nv", type: "button", onclick: logout }, h("span", { class: "g", "aria-hidden": "true" }, "⎋"), h("span", { class: "lb" }, "Esci")),
        h("div", { class: "who" }, user ? `Connesso come ${user}` : "")));
  }

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST" }); } catch (err) { console.warn("Uscita non confermata", err); }
    location.reload();
  }

  store.subscribe((state, changed) => {
    if (changed.includes("level")) { renderLevels(); renderNav(); }
    if (["route", "user", "favorites"].some((key) => changed.includes(key))) renderNav();
    if (changed.includes("link")) {
      linkDot.classList.toggle("down", !state.link);
      linkDot.setAttribute("aria-label", state.link ? "Collegato ad Atena" : "Collegamento con Atena perso");
    }
  });
  renderLevels();
  renderNav();
  onSummary(renderNav);

  return {
    outlet,
    show(route, render) {
      const z = zone(route.id);
      if (z && !allows(z.min)) { go("home"); return; }
      if (z?.added) { markSeen(`zone:${z.id}:${z.added}`); renderNav(); }
      title.textContent = z ? z.title : route.id === "tool" ? "Strumento" : "Nexus";
      document.title = `${title.textContent} · Atena Nexus`;
      render(outlet, route);
      outlet.scrollTop = 0;
    },
  };
}
