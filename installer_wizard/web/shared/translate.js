(function (global) {
  "use strict";
  const LANGS = ["it", "en", "fr"];
  const TABLES = { en: "pairs", fr: "fr", it: "reverse" };
  const ATTRS = ["placeholder", "title", "aria-label", "alt"];
  const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "CODE", "PRE", "NOSCRIPT"]);
  const state = { lang: "it", exact: new Map(), patterns: [], ready: false, observer: null };

  function cached() {
    try { return localStorage.getItem("atena_ui_lang") || ""; } catch (e) { return ""; }
  }

  function pick() {
    const code = (global.ATENA_UI_LANG || cached() || document.documentElement.lang || navigator.language || "it").slice(0, 2).toLowerCase();
    return LANGS.includes(code) ? code : "it";
  }

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

  function build(pairs, lang) {
    const exact = new Map(), patterns = [];
    for (const pair of pairs) {
      const source = pair[0], target = pair[1];
      if (!source || !target || source === target) continue;
      if (/\{\d+\}/.test(source)) {
        const order = [];
        const re = new RegExp("^" + escapeRe(source).replace(/\\\{(\d+)\\\}/g, (m, n) => { order.push(Number(n)); return "(.+?)"; }) + "$", "s");
        patterns.push({ re, order, target });
      } else {
        exact.set(source, target);
      }
    }
    patterns.sort((a, b) => b.re.source.length - a.re.source.length);
    return { exact, patterns };
  }

  function translate(text) {
    if (!text || !state.ready) return text;
    const core = text.trim();
    if (!core || core.length > 2000) return text;
    const norm = core.replace(/\s+/g, " ");
    let out = state.exact.get(norm);
    if (out === undefined && /\S/.test(norm)) {
      for (const p of state.patterns) {
        const m = p.re.exec(norm);
        if (m) {
          out = p.target.replace(/\{(\d+)\}/g, (all, n) => { const i = p.order.indexOf(Number(n)); return i >= 0 ? translate(m[i + 1]) : all; });
          break;
        }
      }
    }
    if (out === undefined) return text;
    const lead = text.match(/^\s*/)[0], tail = text.match(/\s*$/)[0];
    return lead + out + tail;
  }

  function skipped(el) {
    return !el || SKIP.has(el.tagName) || (el.closest && el.closest("[data-no-i18n],[contenteditable=true]"));
  }

  function textNode(node) {
    if (skipped(node.parentElement)) return;
    if (node.__jt !== node.nodeValue) node.__src = node.nodeValue;
    const next = translate(node.__src);
    if (next !== node.nodeValue) node.nodeValue = next;
    node.__jt = node.nodeValue;
  }

  function localized(el, key, current, apply) {
    el.__src = el.__src || {};
    el.__jt = el.__jt || {};
    if (el.__jt[key] !== current) el.__src[key] = current;
    const next = translate(el.__src[key]);
    if (next !== current) apply(next);
    el.__jt[key] = next;
  }

  function element(el) {
    if (skipped(el)) return;
    for (const name of ATTRS) {
      const value = el.getAttribute(name);
      if (value) localized(el, name, value, (next) => el.setAttribute(name, next));
    }
    if (el.tagName === "INPUT" && (el.type === "button" || el.type === "submit") && el.value) {
      localized(el, "value", el.value, (next) => { el.value = next; });
    }
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) return textNode(root);
    if (root.nodeType !== 1 && root.nodeType !== 9 && root.nodeType !== 11) return;
    if (root.nodeType === 1) element(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      node.nodeType === 3 ? textNode(node) : element(node);
      node = walker.nextNode();
    }
  }

  function observe() {
    if (state.observer || !global.MutationObserver) return;
    state.observer = new MutationObserver((records) => {
      for (const r of records) {
        if (r.type === "characterData") textNode(r.target);
        else if (r.type === "attributes") element(r.target);
        else r.addedNodes.forEach(walk);
      }
    });
    state.observer.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  async function load(lang) {
    const v = global.ATENA_ASSET_V ? `?v=${global.ATENA_ASSET_V}` : "";
    const data = await (await fetch(`/static/shared/i18n_catalog.json${v}`, { cache: "force-cache" })).json();
    const built = build(data[TABLES[lang]] || [], lang);
    state.lang = lang;
    state.exact = built.exact;
    state.patterns = built.patterns;
    state.ready = true;
    document.documentElement.lang = lang;
    walk(document.body);
    document.dispatchEvent(new CustomEvent("atena-translated", { detail: lang }));
  }

  async function start(lang) {
    state.lang = lang || pick();
    document.documentElement.lang = state.lang;
    try {
      await load(state.lang);
      observe();
    } catch (e) {
      console.warn("i18n catalog unavailable", e);
    }
  }

  function remember(lang) {
    try { localStorage.setItem("atena_ui_lang", lang); } catch (e) { console.warn("language preference not saved", e); }
    global.ATENA_UI_LANG = lang;
    return fetch("/api/locale/ui", {
      method: "PUT", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Atena-Request": "1" },
      body: JSON.stringify({ lang }),
    }).then((r) => { if (!r.ok) console.warn("language preference not saved", r.status); })
      .catch((e) => console.warn("language preference not saved", e));
  }

  async function switchTo(lang, persist = true) {
    if (!LANGS.includes(lang) || lang === state.lang) return;
    if (persist) remember(lang);
    await load(lang);
  }

  function setLanguage(lang) {
    if (!LANGS.includes(lang)) return Promise.resolve();
    return remember(lang).finally(() => location.reload());
  }

  global.AtenaI18n = { start, setLanguage, switchTo, translate, language: () => state.lang, languages: LANGS };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => start());
  else start();
})(window);
