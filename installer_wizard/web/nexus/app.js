import { h, mount } from "./core/dom.js";
import { api, onUnauthorized, stream } from "./core/http.js";
import { LEVELS, allows, applyLevel, cachedLevel, chooseLevel } from "./core/level.js";
import { current, define, go, setFallback, start, view } from "./core/router.js";
import { store } from "./core/store.js";
import { fail, toast } from "./core/toast.js";
import { startSummary, summary } from "./core/summary.js";
import { addSource, installShortcut } from "./components/palette.js";
import { renderLogin } from "./features/login/login.js";
import { createShell } from "./features/shell/shell.js";
import { ZONES } from "./features/shell/zones.js";
import { renderHome } from "./features/home/home.js";
import { renderZone } from "./features/zone/zone.js";
import { renderTool } from "./features/tool/tool.js";
import { renderAwakening } from "./features/awakening/awakening.js";
import { renderFlows } from "./features/flows/flows.js";
import { renderSection, sections } from "./features/section/section.js";
import { renderWidgets } from "./features/widgets/widgets.js";
import { cachedWidgets, recall, widgets } from "./core/widgets.js";

const root = document.getElementById("nexus");

function registerRoutes() {
  for (const z of ZONES) define(z.id, renderZone);
  define("home", renderHome);
  define("tool", renderTool);
  define("awakening", renderAwakening);
  define("flows", renderFlows);
  define("section", renderSection);
  define("classic", renderSection);
  define("widgets", renderWidgets);
  setFallback("home");
}

function registerPalette() {
  addSource(() => ZONES.filter((z) => allows(z.min)).map((z) => ({
    glyph: z.glyph, title: z.title, kind: "Zona", keywords: z.lead, run: () => go(z.id),
  })));
  addSource(() => LEVELS.map((l) => ({
    glyph: "◍", title: `Passa al livello ${l.label}`, kind: "Azione", keywords: `livello ${l.hint}`,
    run: () => chooseLevel(l.id).then(() => toast(`Livello ${l.label}`)).catch(fail),
  })));
  addSource(() => (summary()?.tools || []).filter((t) => allows(t.level)).map((t) => ({
    glyph: t.icon, title: t.name, kind: t.badge === "new" ? "Strumento · Novità" : t.badge === "updated" ? "Strumento · Aggiornato" : "Strumento", keywords: `${t.description} ${t.id}`, run: () => go("tool", t.id),
  })));
  addSource(() => sections().filter((s) => allows(s.zone.min)).map((s) => ({
    glyph: s.zone.glyph, title: s.label, kind: `Sezione · ${s.zone.title}`, keywords: s.tab, run: () => go("section", s.tab),
  })));
  addSource(() => cachedWidgets().map((w) => ({
    glyph: w.icon || "▣", title: w.name, kind: "Widget · mostra sul display", keywords: `widget ${w.description || ""} ${w.id}`,
    run: () => recall(w).catch(fail),
  })));
  addSource(() => [{ glyph: "▤", title: "Apri il pannello classico", kind: "Azione", keywords: "vecchio admin", run: () => location.assign("/classic") }]);
}

async function loadPreferences() {
  try {
    const prefs = await api("/api/nexus/preferences");
    applyLevel(prefs.level);
    store.set({ level: prefs.level, favorites: prefs.favorites });
  } catch (err) {
    fail(err);
  }
}

async function enter(user) {
  store.set({ user });
  await loadPreferences();
  const shell = createShell(root);
  startSummary().catch(fail);
  widgets().catch(() => {});
  stream("/api/stream", (snapshot) => store.set({ snapshot }), (link) => store.set({ link }));
  start((route) => shell.show(route, view(route.id)));
  store.subscribe((_, changed) => {
    if (changed.includes("level")) { const route = current(); shell.show(route, view(route.id)); }
  });
}

async function boot() {
  const level = cachedLevel();
  if (level) { applyLevel(level); store.set({ level }); }
  registerRoutes();
  registerPalette();
  installShortcut();
  onUnauthorized(() => { if (store.get().user) location.reload(); });
  try {
    const me = await api("/api/auth/me");
    await enter(me.user);
  } catch (err) {
    if (err.status === 401) renderLogin(root, enter);
    else mount(root, h("main", { class: "login" }, h("div", { class: "panel login-card" },
      h("h1", {}, "A.T.E.N.A."), h("p", { class: "login-err" }, err.message),
      h("button", { class: "btn primary", type: "button", onclick: () => location.reload() }, "Riprova"))));
  }
}

boot();
