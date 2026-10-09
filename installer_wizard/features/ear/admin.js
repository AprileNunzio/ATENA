(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const KEEP = ["ATENA_EAR_MODE", "ATENA_ONLINE_STT_PROVIDER", "ATENA_ONLINE_STT_KEY", "ATENA_ONLINE_STT_URL", "ATENA_ONLINE_STT_MODEL"];
  let step = "listen", saved = {}, draft = {}, defaults = {}, typedKey = "", review = null;

  const feature = () => ((A.featData && A.featData.features) || []).find((f) => f.id === "ear");
  const changed = () => Object.keys(draft).filter((k) => draft[k] !== saved[k] && !(k === "ATENA_ONLINE_STT_KEY" && !typedKey));
  const stepOf = (id) => A.earSchema.STEPS.find((s) => s.id === id);
  const visible = (f) => !f.when || f.when(draft);

  function summary(id) {
    const v = draft;
    if (id === "listen") {
      const mode = { offline: "Offline", online: "Online", hybrid: "Ibrido" }[v.ATENA_EAR_MODE] || "Offline";
      const prov = (A.earSchema.PROVIDERS.find((p) => p.value === v.ATENA_ONLINE_STT_PROVIDER) || {}).title;
      return v.ATENA_EAR_MODE === "offline" ? mode : `${mode} · ${prov || ""}`;
    }
    if (id === "who") return v.ATENA_VOICEPRINT_ENFORCE === "1" ? "Solo voci registrate" : "Chiunque dica «Atena»";
    if (id === "mic") return (preset() || {}).title || "Personalizzato";
    return v.ATENA_EAR_RECORD === "0" ? "Nessuna registrazione" : `Registrazioni per ${v.ATENA_EAR_RECORD_HOURS || "?"} h`;
  }

  function preset() {
    const field = stepOf("mic").fields.find((f) => f.kind === "preset");
    return field.options.find((o) => Object.entries(o.set).every(([k, val]) => String(draft[k]) === val));
  }

  function renderSteps() {
    $("ear-steps").innerHTML = A.earSchema.STEPS.map((s, i) => `<button type="button" class="ear-step ${s.id === step ? "on" : ""}" data-step="${s.id}">
      <span class="ear-step-n">${i + 1}</span><span class="ear-step-ic">${s.icon}</span>
      <span class="ear-step-t"><b>${fmt.esc(s.title)}</b><small>${fmt.esc(summary(s.id))}</small></span></button>`).join("");
  }

  function cards(f, value) {
    return `<div class="ear-cards">${f.options.map((o) => `<button type="button" class="ear-card ${String(value) === o.value ? "on" : ""}" data-key="${f.key || ""}" data-value="${fmt.esc(o.value)}">
      <span class="ear-card-ic">${o.icon || ""}</span><b>${fmt.esc(o.title)}</b><small>${fmt.esc(o.text || "")}</small>
      ${o.link && String(value) === o.value ? `<a href="${fmt.esc(o.link)}" target="_blank" rel="noopener noreferrer">Ottieni la chiave ↗</a>` : ""}</button>`).join("")}</div>`;
  }

  function field(f) {
    const v = draft[f.key] ?? "";
    const wrap = (inner) => `<div class="ear-field ${f.expert ? "x-expert" : ""}"><label>${fmt.esc(f.label)}</label>${inner}</div>`;
    if (f.kind === "cards") return wrap(cards(f, v));
    if (f.kind === "preset") {
      const now = preset();
      return wrap(`<div class="ear-cards">${f.options.map((o) => `<button type="button" class="ear-card ${now && now.value === o.value ? "on" : ""}" data-preset="${o.value}">
        <span class="ear-card-ic">${o.icon}</span><b>${fmt.esc(o.title)}</b><small>${fmt.esc(o.text)}</small></button>`).join("")}</div>`);
    }
    if (f.kind === "toggle") return `<label class="ear-toggle ${f.expert ? "x-expert" : ""}"><span>${fmt.esc(f.label)}</span>
      <input type="checkbox" data-toggle="${f.key}" data-on="${f.on}" data-off="${f.off}" ${String(v) === f.on ? "checked" : ""}><i></i></label>`;
    if (f.kind === "slider") {
      const num = Number(v === "" ? f.min : v);
      return wrap(`<div class="ear-slider"><input type="range" min="${f.min}" max="${f.max}" step="${f.step}" value="${num}" data-slider="${f.key}">
        <output>${fmt.esc(String(num).replace(".", ","))}${f.unit ? ` ${f.unit}` : ""}</output></div>
        ${f.left ? `<div class="ear-ends"><span>${fmt.esc(f.left)}</span><span>${fmt.esc(f.right)}</span></div>` : ""}`);
    }
    if (f.kind === "select") return wrap(`<select data-input="${f.key}">${f.options.map((o) => `<option value="${fmt.esc(o.value)}" ${String(v) === o.value ? "selected" : ""}>${fmt.esc(o.title)}</option>`).join("")}</select>`);
    if (f.kind === "text") return wrap(`<input data-input="${f.key}" value="${fmt.esc(v)}" placeholder="${fmt.esc(f.placeholder || "")}" autocomplete="off">`);
    if (f.kind === "apikey") {
      const stored = saved[f.key] && !typedKey;
      return wrap(`<div class="ear-key"><input type="password" id="ear-key" autocomplete="off" placeholder="${stored ? `Chiave salvata (${fmt.esc(saved[f.key])}): incollane una nuova per cambiarla` : "Incolla qui la chiave API"}" value="${fmt.esc(typedKey)}">
        <button type="button" class="btn" id="ear-check">Verifica</button></div><div class="ear-keymsg" id="ear-keymsg"></div>`);
    }
    if (f.kind === "actions") {
      const r = review || {}, s = r.summary || {};
      return `<div class="ear-actions"><div class="muted-note">Stato dell'analisi: ${fmt.esc(r.state || "—")}${s.chunks != null ? ` · ${s.chunks} blocchi analizzati` : ""}${r.pending != null ? ` · ${r.pending} in attesa` : ""}</div>
        <div class="row" style="gap:8px; flex-wrap:wrap"><button type="button" class="btn danger" id="ear-purge">Elimina tutte le registrazioni</button>
        <button type="button" class="btn" id="ear-retune">Azzera le regolazioni automatiche</button></div></div>`;
    }
    return "";
  }

  function render() {
    renderSteps();
    const s = stepOf(step);
    $("ear-body").innerHTML = `<div class="ear-body-head"><div class="panel-title" style="margin:0">${s.icon} ${fmt.esc(s.title)}</div><div class="muted-note">${fmt.esc(s.hint)}</div></div>
      ${s.fields.filter(visible).map(field).join("")}
      <div class="ear-nav">${s === A.earSchema.STEPS[0] ? "<span></span>" : '<button type="button" class="btn" data-go="-1">← Indietro</button>'}
        ${s === A.earSchema.STEPS[A.earSchema.STEPS.length - 1] ? "" : '<button type="button" class="btn primary" data-go="1">Avanti →</button>'}</div>`;
    const n = changed().length;
    $("ear-savebar").hidden = !n;
    $("ear-changes").textContent = n === 1 ? "1 modifica da salvare" : `${n} modifiche da salvare`;
    $("ear-summary").textContent = A.earSchema.STEPS.map((x) => summary(x.id)).join(" · ");
  }

  function set(key, value) { draft[key] = String(value); render(); }

  async function load() {
    const f = feature();
    if (!f) { $("ear-body").textContent = "Funzionalità non trovata"; return; }
    defaults = Object.fromEntries((f.settings || []).map((s) => [s.key, s.default ?? ""]));
    saved = { ...defaults, ...(f.values || {}) };
    draft = { ...saved }; typedKey = "";
    render();
    try { review = await A.api("GET", "/api/ear/review"); if (step === "learn") render(); } catch (e) { review = { state: e.message }; }
  }

  async function save() {
    const body = Object.fromEntries(changed().map((k) => [k, k === "ATENA_ONLINE_STT_KEY" ? typedKey : draft[k]]));
    try {
      await A.api("PUT", "/api/features/ear/settings", body);
      A.toast("Ascolto aggiornato: si riavvia in pochi secondi");
      await A.loadFeatures();
      load();
    } catch (e) { A.toast(e.message, true); }
  }

  async function checkKey() {
    const msg = $("ear-keymsg");
    msg.textContent = "Verifico…"; msg.className = "ear-keymsg";
    try {
      const r = await A.api("POST", "/api/ear/stt/check", { provider: draft.ATENA_ONLINE_STT_PROVIDER, key: typedKey, url: draft.ATENA_ONLINE_STT_URL || "" });
      msg.textContent = r.message; msg.className = `ear-keymsg ${r.ok ? "ok" : "bad"}`;
    } catch (e) { msg.textContent = e.message; msg.className = "ear-keymsg bad"; }
  }

  function init() {
    $("ear-steps").addEventListener("click", (e) => { const b = e.target.closest("[data-step]"); if (b) { step = b.dataset.step; render(); } });
    const body = $("ear-body");
    body.addEventListener("click", async (e) => {
      const t = e.target;
      if (t.closest("a")) return;
      const card = t.closest("[data-key][data-value]");
      if (card) return set(card.dataset.key, card.dataset.value);
      const pre = t.closest("[data-preset]");
      if (pre) {
        const opt = stepOf("mic").fields.find((f) => f.kind === "preset").options.find((o) => o.value === pre.dataset.preset);
        Object.assign(draft, opt.set); return render();
      }
      const go = t.closest("[data-go]");
      if (go) {
        const i = A.earSchema.STEPS.findIndex((s) => s.id === step) + Number(go.dataset.go);
        step = A.earSchema.STEPS[Math.max(0, Math.min(A.earSchema.STEPS.length - 1, i))].id; return render();
      }
      if (t.id === "ear-check") return checkKey();
      try {
        if (t.id === "ear-purge" && confirm("Eliminare tutte le registrazioni della voce?")) { const r = await A.api("POST", "/api/ear/review/purge"); A.toast(`${r.removed} file eliminati`); load(); }
        if (t.id === "ear-retune" && confirm("Azzerare le regolazioni che Atena ha fatto da sola?")) { await A.api("POST", "/api/ear/tuning/reset"); A.toast("Regolazioni azzerate"); }
      } catch (err) { A.toast(err.message, true); }
    });
    body.addEventListener("input", (e) => {
      const t = e.target;
      if (t.dataset.slider) { draft[t.dataset.slider] = t.value; t.nextElementSibling.textContent = t.value.replace(".", ","); renderSteps(); $("ear-savebar").hidden = !changed().length; $("ear-changes").textContent = `${changed().length} modifiche da salvare`; }
      if (t.id === "ear-key") { typedKey = t.value.trim(); draft.ATENA_ONLINE_STT_KEY = typedKey ? "new" : saved.ATENA_ONLINE_STT_KEY; $("ear-savebar").hidden = !changed().length; $("ear-changes").textContent = `${changed().length} modifiche da salvare`; }
    });
    body.addEventListener("change", (e) => {
      const t = e.target;
      if (t.dataset.toggle) set(t.dataset.toggle, t.checked ? t.dataset.on : t.dataset.off);
      if (t.dataset.input) set(t.dataset.input, t.value.trim());
    });
    $("ear-save").addEventListener("click", save);
    $("ear-undo").addEventListener("click", () => { draft = { ...saved }; typedKey = ""; render(); });
    $("ear-defaults").addEventListener("click", () => {
      Object.entries(defaults).forEach(([k, v]) => { if (!KEEP.includes(k)) draft[k] = String(v); });
      render(); A.toast("Valori consigliati pronti: premi «Salva e applica»");
    });
  }

  A.tab("ear", { title: "Ascolto vocale", init, load });
})();
