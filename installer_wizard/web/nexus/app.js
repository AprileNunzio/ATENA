import { h, mount } from "./core/dom.js";
import { api, onUnauthorized, stream } from "./core/http.js";
import { LEVELS, allows, applyLevel, cachedLevel, chooseLevel } from "./core/level.js";
import { define, go, setFallback, start, view } from "./core/router.js";
import { store } from "./core/store.js";
import { fail, toast } from "./core/toast.js";
import { startSummary, summary } from "./core/summary.js";
import { classicHref } from "./components/tool-card.js";
import { addSource, installShortcut } from "./components/palette.js";
import { renderLogin } from "./features/login/login.js";
import { createShell } from "./features/shell/shell.js";
import { ZONES } from "./features/shell/zones.js";
import { renderHome } from "./features/home/home.js";
import { renderZone } from "./features/zone/zone.js";

const root = document.getElementById("nexus");

function registerRoutes() {
  for (const z of ZONES) define(z.id, renderZone);
  define("home", renderHome);
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
    glyph: t.icon, title: t.name, kind: "Strumento", keywords: `${t.description} ${t.id}`, run: () => location.assign(classicHref(t)),
  })));
  addSource(() => [{ glyph: "▤", title: "Apri il pannello classico", kind: "Azione", keywords: "vecchio admin", run: () => location.assign("/") }]);
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
  stream("/api/stream", (snapshot) => store.set({ snapshot }), (link) => store.set({ link }));
  start((route) => shell.show(route, view(route.id)));
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
