import { h } from "../../core/dom.js";
import { api } from "../../core/http.js";
import { LEVELS, chooseLevel } from "../../core/level.js";
import { store } from "../../core/store.js";

const setMode = (fid, mode) => api(`/api/features/${fid}`, { method: "PUT", body: { mode } });
const setSettings = (fid, body) => api(`/api/features/${fid}/settings`, { method: "PUT", body });

export const STEPS = {
  language: {
    label: "Lingua", title: "Ciao, sono Atena. Come ti chiami?",
    text: "Ti chiamerò così e userò la lingua che scegli per il pannello e per il display.",
    init: (c) => ({ name: c.name, lang: c.lang }),
    form: (a, set) => [
      h("div", { class: "field" }, h("label", { for: "aw-name" }, "Il tuo nome"),
        h("input", { class: "input", id: "aw-name", maxlength: "40", autocomplete: "given-name", value: a.name || "", oninput: (e) => set({ name: e.target.value }, false) })),
      choices([["it", "Italiano", "Voce italiana"], ["en", "English", "English voice"], ["fr", "Français", "Voix française"]], a.lang, (lang) => set({ lang })),
    ],
    valid: (a) => Boolean(a.lang),
    async apply(a) {
      const name = (a.name || "").trim().slice(0, 40);
      if (name) await api("/api/config", { method: "PUT", body: { ATENA_USER_NAME: name } });
      await api("/api/locale/ui", { method: "PUT", body: { lang: a.lang } });
      return [name, a.lang.toUpperCase()].filter(Boolean).join(" · ");
    },
  },
  level: {
    label: "Livello", title: "Quanto vuoi vedere sotto il cofano?",
    text: "Puoi cambiare idea quando vuoi dall'interruttore in alto.",
    init: () => ({ level: store.get().level }),
    form: (a, set) => [choices(LEVELS.map((l) => [l.id, l.label, l.hint]), a.level, (level) => set({ level }))],
    valid: (a) => Boolean(a.level),
    async apply(a) { await chooseLevel(a.level); return LEVELS.find((l) => l.id === a.level).label; },
  },
  brain: {
    label: "Cervello", title: "Dove deve pensare Atena?",
    text: "Il cervello è il modello che capisce e risponde. Su questo computer i dati non escono mai di casa.",
    init: (c) => ({ brain: c.brain, url: c.ollama_url }),
    form: (a, set) => [
      choices([["local", "Su questo computer", "Privato, funziona anche senza internet"], ["remote", "Su un altro computer", "Usa la scheda video di un PC della rete"],
        ["cloud", "Nel cloud", "Il più intelligente, serve una chiave"]], a.brain, (brain) => set({ brain })),
      a.brain === "remote" ? h("div", { class: "field" }, h("label", { for: "aw-url" }, "Indirizzo del computer con Ollama"),
        h("input", { class: "input", id: "aw-url", placeholder: "192.168.1.20", maxlength: "120", value: a.url || "", oninput: (e) => set({ url: e.target.value }, false) })) : null,
      a.brain === "cloud" ? h("p", { class: "aw-note" }, "Dopo il Risveglio inserisci la chiave del servizio in Cervello → Cloud.") : null,
    ],
    valid: (a) => Boolean(a.brain) && (a.brain !== "remote" || Boolean((a.url || "").trim())),
    async apply(a, current) {
      if (a.brain !== current.brain || a.brain === "remote") await api("/api/packages/brain", { method: "POST", body: { mode: a.brain, url: (a.url || "").trim() } });
      return { local: "Su questo computer", remote: "Su un altro computer", cloud: "Nel cloud" }[a.brain];
    },
  },
  senses: {
    label: "Sensi", title: "Quali sensi posso usare?",
    text: "Ogni senso resta spento finché non lo accendi. Le immagini e la voce restano in casa.",
    init: (c) => ({ senses: Object.entries(c.senses).filter(([, m]) => m && m !== "0").map(([id]) => id) }),
    form: (a, set, c) => [h("div", { class: "choices" }, [["vision", "◐", "Vista", "Riconosco volti e oggetti"], ["ear", "◖", "Udito", "Mi chiami con «Ehi Atena»"],
      ["hands", "☚", "Mani", "Comandi con i gesti"]].filter(([id]) => id in c.senses).map(([id, glyph, title, hint]) => {
      const on = a.senses.includes(id);
      return h("button", { type: "button", class: "choice", role: "switch", "aria-checked": String(on), "aria-pressed": String(on),
        onclick: () => set({ senses: on ? a.senses.filter((s) => s !== id) : [...a.senses, id] }) },
      h("span", { class: "cg", "aria-hidden": "true" }, glyph), h("b", {}, title), h("span", {}, hint));
    }))],
    valid: () => true,
    async apply(a, current) {
      for (const id of Object.keys(current.senses)) {
        const want = a.senses.includes(id) ? "auto" : "0";
        if ((current.senses[id] === "0") !== (want === "0")) await setMode(id, want);
      }
      return a.senses.length ? `${a.senses.length} sensi attivi` : "Nessun senso";
    },
  },
  home: {
    label: "Casa", title: "Colleghiamo la tua casa?",
    text: "Con Home Assistant posso accendere luci, scene e clima.",
    init: (c) => ({ choice: c.home.connected ? "keep" : "", url: c.home.url, token: "" }),
    form: (a, set, c) => [
      choices([...(c.home.connected ? [["keep", "Già collegata", c.home.url]] : []), ["connect", "Collegala ora", "Serve l'indirizzo e un token"],
        ["later", "Più tardi", "La trovi in Strumenti → Casa"]], a.choice, (choice) => set({ choice })),
      a.choice === "connect" ? h("div", { class: "aw-grid" },
        h("div", { class: "field" }, h("label", { for: "aw-ha" }, "Indirizzo di Home Assistant"),
          h("input", { class: "input", id: "aw-ha", placeholder: "http://192.168.1.40:8123", maxlength: "200", value: a.url || "", oninput: (e) => set({ url: e.target.value }, false) })),
        h("div", { class: "field" }, h("label", { for: "aw-tk" }, "Token di accesso a lunga durata"),
          h("input", { class: "input", id: "aw-tk", type: "password", autocomplete: "new-password", maxlength: "500", oninput: (e) => set({ token: e.target.value }, false) }))) : null,
    ],
    valid: (a) => Boolean(a.choice) && (a.choice !== "connect" || (/^https?:\/\/\S+$/.test((a.url || "").trim()) && Boolean(a.token))),
    async apply(a) {
      if (a.choice === "connect") {
        await setSettings("home_assistant", { HOME_ASSISTANT_URL: a.url.trim(), HOME_ASSISTANT_TOKEN: a.token.trim() });
        await setMode("home_assistant", "auto");
        return "Collegata";
      }
      return a.choice === "keep" ? "Già collegata" : "Più tardi";
    },
  },
  trust: {
    label: "Fiducia", title: "Quanto posso fare da sola?",
    text: "Le Leggi di Atena valgono sempre. Qui scegli quando devo chiederti il permesso.",
    init: (c) => ({ profile: c.trust }),
    form: (a, set) => [choices([["careful", "Prudente", "Non agisco mai da sola, ti chiedo tutto"], ["balanced", "Equilibrata", "Propongo e agisco solo quando è sicuro"],
      ["autonomous", "Autonoma", "Agisco da sola e ti avviso; accesso completo agli strumenti"]], a.profile, (profile) => set({ profile }))],
    valid: (a) => Boolean(a.profile),
    async apply(a, current, profiles) {
      const p = profiles[a.profile];
      await setMode("autonomy", p.autonomy);
      await setSettings("agent", { ATENA_AGENT_ACCESS: p.agent_access });
      return { careful: "Prudente", balanced: "Equilibrata", autonomous: "Autonoma" }[a.profile];
    },
  },
};

function choices(items, value, pick) {
  return h("div", { class: "choices", role: "radiogroup" }, items.map(([id, title, hint]) => h("button", {
    type: "button", class: "choice", role: "radio", "aria-checked": String(value === id), "aria-pressed": String(value === id), onclick: () => pick(id),
  }, h("b", {}, title), hint ? h("span", {}, hint) : null)));
}
