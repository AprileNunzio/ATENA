(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const NAME_RE = /^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ-]{0,39}$/u;
  const FLOW = ["intro", "profile", "voice", "home", "privacy"];
  const OPTIONAL = new Set(["home"]);
  const choice = { lang: "it", profile: "auto", voice: "if_sara" };
  let info = null;
  let order = [];
  let at = 0;
  let code = "";
  let busy = false;
  let audio = null;

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const error = (msg) => { $("error").textContent = msg || ""; };

  async function call(path, { body, file, raw } = {}) {
    const headers = { "X-Atena-Request": "1" };
    if (code) headers["X-Atena-Setup-Code"] = code;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (file) headers["Content-Type"] = "application/octet-stream";
    const r = await fetch(path, {
      method: "POST", headers, credentials: "same-origin", cache: "no-store",
      body: file || (body !== undefined ? JSON.stringify(body) : undefined),
    });
    if (r.status === 410) { location.replace("/"); throw new Error(""); }
    if (!r.ok) {
      let detail = "Qualcosa non ha funzionato, riprova";
      try { detail = (await r.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return raw ? r : r.json();
  }

  function radio(container, items, key, build) {
    container.replaceChildren();
    for (const [value, data] of items) {
      const b = build(value, data);
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", String(choice[key] === value));
      b.addEventListener("click", (e) => {
        if (e.target.closest(".play")) return;
        choice[key] = value;
        for (const other of container.children) other.setAttribute("aria-checked", String(other === b));
      });
      container.append(b);
    }
  }

  function render() {
    radio($("langs"), Object.entries(info.languages), "lang", (_, label) => {
      const b = el("button", null, label);
      b.type = "button";
      return b;
    });

    const hw = info.hardware;
    $("hw").textContent = hw.gpu
      ? `Ho trovato ${hw.ram_gb} GB di memoria, ${hw.cpu} processori, una scheda video e ${hw.disk_free_gb} GB liberi sul disco.`
      : `Ho trovato ${hw.ram_gb} GB di memoria, ${hw.cpu} processori e ${hw.disk_free_gb} GB liberi sul disco.`;
    choice.profile = hw.recommended;
    radio($("profiles"), Object.entries(info.profiles), "profile", (id, p) => {
      const b = el("button", "choice");
      b.type = "button";
      const meta = el("span", "meta");
      if (id === hw.recommended) meta.append(el("span", "badge", "Consigliato"));
      if (p.size_gb) meta.append(el("span", null, `${p.size_gb} GB`));
      b.append(el("b", null, p.label), meta, el("small", null, p.note));
      return b;
    });

    radio($("voices"), Object.entries(info.voices), "voice", (id, label) => {
      const b = el("button", "choice");
      b.type = "button";
      const play = el("span", "play", "▶");
      play.setAttribute("role", "button");
      play.setAttribute("tabindex", "0");
      play.setAttribute("aria-label", "Ascolta");
      const listen = () => preview(id, play);
      play.addEventListener("click", listen);
      play.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); listen(); } });
      const meta = el("span", "meta");
      meta.append(play);
      const [name, ...rest] = label.split(" — ");
      b.append(el("b", null, name), meta, el("small", null, rest.join(" — ")));
      return b;
    });

    $("name").value = info.current.name || "";
    choice.lang = info.current.lang in info.languages ? info.current.lang : "it";
    if (info.code) {
      $("local-code-value").textContent = info.code;
      $("local-code").hidden = false;
    }
    if (info.wakeword) $("wake-label").textContent = "Modello «Ehi, Atena» già presente: caricane uno nuovo se vuoi";
  }

  async function preview(id, button) {
    error();
    if (audio) { audio.pause(); audio = null; }
    document.querySelectorAll(".play.playing").forEach((p) => p.classList.remove("playing"));
    button.classList.add("playing");
    try {
      const r = await call(`/api/setup/voice?voice=${encodeURIComponent(id)}`, { raw: true });
      const url = URL.createObjectURL(await r.blob());
      audio = new Audio(url);
      audio.addEventListener("ended", () => { button.classList.remove("playing"); URL.revokeObjectURL(url); }, { once: true });
      await audio.play();
    } catch (e) {
      button.classList.remove("playing");
      error(e.message);
    }
  }

  function show() {
    const id = order[at];
    document.querySelectorAll(".screen").forEach((s) => { s.hidden = s.dataset.screen !== id; });
    const dots = $("dots");
    dots.replaceChildren(...FLOW.map((_, i) => el("li", FLOW.indexOf(id) >= i ? "on" : "")));
    $("nav").hidden = id === "done";
    $("back").hidden = at === 0;
    $("skip").hidden = !OPTIONAL.has(id);
    $("next").textContent = id === "privacy" ? "Completa" : id === "code" ? "Verifica" : "Avanti";
    error();
    const focus = document.querySelector(`.screen[data-screen="${id}"] input, .screen[data-screen="${id}"] button`);
    if (focus && matchMedia("(pointer: fine)").matches) focus.focus({ preventScroll: true });
    scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  function validate(id) {
    if (id === "code" && !/^\d{6}$/.test($("code").value.trim())) return "Il codice è di 6 cifre";
    if (id === "intro") {
      const name = $("name").value.trim();
      if (name && !NAME_RE.test(name)) return "Il nome può contenere solo lettere e trattini, senza spazi";
    }
    if (id === "home") {
      const url = $("ha-url").value.trim();
      const token = $("ha-token").value.trim();
      if ((url || token) && !(url && token)) return "Per Home Assistant servono sia l'indirizzo sia il token";
      if (url && !/^https?:\/\/[A-Za-z0-9.-]+(:\d{1,5})?(\/[\w.~/-]*)?$/.test(url)) return "Indirizzo di Home Assistant non valido";
      const tg = $("telegram").value.trim();
      if (tg && !/^\d{5,12}:[A-Za-z0-9_-]{30,64}$/.test(tg)) return "Token di Telegram non valido";
    }
    return "";
  }

  async function finish() {
    const file = $("wake").files[0];
    if (file) await call("/api/setup/wakeword", { file });
    const res = await call("/api/setup", {
      body: {
        name: $("name").value.trim(), lang: choice.lang, profile: choice.profile, voice: choice.voice,
        ha_url: $("ha-url").value.trim(), ha_token: $("ha-token").value.trim(), telegram: $("telegram").value.trim(),
        commercial: $("commercial").checked, shares: $("shares").checked,
      },
    });
    for (const id of ["ha-token", "telegram", "code"]) $(id).value = "";
    code = "";
    if (res.shares_password) {
      $("secret-value").textContent = res.shares_password;
      $("secret").hidden = false;
    }
    order.push("done");
  }

  async function next(skip = false) {
    if (busy) return;
    const id = order[at];
    const problem = skip ? "" : validate(id);
    if (problem) { error(problem); return; }
    busy = true;
    $("next").disabled = true;
    try {
      if (id === "code") {
        code = $("code").value.trim();
        try { await call("/api/setup/verify"); } catch (e) { code = ""; throw e; }
      }
      if (skip && id === "home") for (const f of ["ha-url", "ha-token", "telegram"]) $(f).value = "";
      if (id === "privacy") await finish();
      at = Math.min(at + 1, order.length - 1);
      show();
    } catch (e) {
      error(e.message);
    } finally {
      busy = false;
      $("next").disabled = false;
    }
  }

  $("next").addEventListener("click", () => next());
  $("skip").addEventListener("click", () => next(true));
  $("back").addEventListener("click", () => { if (at > 0) { at--; show(); } });
  $("wiz").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.matches("input:not([type=checkbox]):not([type=file])")) { e.preventDefault(); next(); }
  });
  $("code").addEventListener("input", (e) => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 6); });
  $("wake").addEventListener("change", (e) => {
    const f = e.target.files[0];
    $("upload").classList.toggle("ok", !!f);
    $("wake-label").textContent = f ? `Scelto: ${f.name}` : "Carica il file .onnx (facoltativo)";
    if (f && (f.size < 1024 || f.size > 20 * 1024 * 1024 || !/\.onnx$/i.test(f.name))) {
      e.target.value = "";
      $("upload").classList.remove("ok");
      error("Il modello deve essere un file .onnx tra 1 KB e 20 MB");
    }
  });
  $("copy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("secret-value").textContent);
      $("copy").textContent = "Copiata";
    } catch {
      getSelection().selectAllChildren($("secret-value"));
    }
  });

  fetch("/api/setup", { credentials: "same-origin", cache: "no-store" })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error("La configurazione guidata è disponibile solo dalla rete di casa"))))
    .then((data) => {
      if (!data.needed) { location.replace("/"); return; }
      info = data;
      order = data.local ? [...FLOW] : ["code", ...FLOW];
      render();
      show();
    })
    .catch((e) => error(e.message));
})();
