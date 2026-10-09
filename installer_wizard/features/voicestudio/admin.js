(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const S = { data: null, step: "power", where: "local", url: "", key: "", timer: null, audio: null, busy: false };
  const STEPS = [
    { id: "power", icon: "🔌", title: "Accendi" },
    { id: "create", icon: "✨", title: "Crea una voce" },
    { id: "voices", icon: "🎵", title: "Le mie voci" },
  ];
  A.vs = S;

  const ready = () => !!(S.data && S.data.enabled && S.data.online);
  const installing = () => !!(S.data && S.data.enabled && !S.data.online && S.data.where === "local" && (S.data.install || {}).status !== "failed");

  function light() {
    const d = S.data || {}, el = $("vs-light");
    const [cls, text] = !d.enabled ? ["", "Spento"] : ready() ? ["ok", "Pronto"] : installing() ? ["wait", "Si sta preparando"]
      : d.error ? ["bad", "Non risponde"] : ["wait", "Si sta accendendo"];
    el.className = `vs-light ${cls}`;
    $("vs-light-text").textContent = text;
  }

  function summary(id) {
    const d = S.data || {};
    if (id === "power") return !d.enabled ? "Spento" : d.where === "remote" ? "Su un altro computer" : "Su questo computer";
    if (id === "create") return ready() ? "Inventala o copiala" : "Prima accendi lo Studio";
    const n = (d.voices || []).length;
    return n === 1 ? "1 voce" : `${n} voci`;
  }

  function renderSteps() {
    $("vs-steps").innerHTML = STEPS.map((s, i) => `<button type="button" class="vs-step ${s.id === S.step ? "on" : ""}" data-step="${s.id}" ${i && !ready() ? "disabled" : ""}>
      <span class="vs-step-n">${i + 1}</span><span class="vs-step-ic">${s.icon}</span>
      <span class="vs-step-t"><b>${fmt.esc(s.title)}</b><small>${fmt.esc(summary(s.id))}</small></span></button>`).join("");
  }

  function card(key, value, icon, title, text) {
    return `<button type="button" class="vs-card ${S[key] === value ? "on" : ""}" data-set="${key}" data-value="${value}">
      <span class="vs-ic">${icon}</span><b>${fmt.esc(title)}</b><small>${fmt.esc(text)}</small></button>`;
  }

  function powerHtml() {
    const d = S.data || {}, inst = d.install || {};
    const status = !d.enabled ? "" : ready() ? `<div class="vs-msg ok">✅ Lo Studio è pronto. Vai al passo 2 per creare una voce.</div>`
      : installing() ? `<div><div class="vs-label">${fmt.esc(["running", "retrying"].includes(inst.status) && inst.message ? inst.message : "In coda: l'installazione parte tra poco")}</div><div class="vs-progress"><i style="width:${Math.max(4, Number(inst.progress) || 0)}%"></i></div>
          <div class="muted-note">La prima volta scarica circa 6 GB: può volerci un po'. Puoi chiudere questa pagina.</div></div>`
      : `<div class="vs-msg bad">⚠ ${fmt.esc(d.where === "remote" ? "L'altro computer non risponde: controlla che VoiceStudio sia acceso e che indirizzo e chiave siano giusti." : "L'installazione non è riuscita: premi «Riprova».")}</div>
        ${d.where === "local" ? '<div class="vs-row"><button type="button" class="btn vs-big" id="vs-retry">🔁 Riprova</button></div>' : ""}
        ${inst.error || d.error ? `<div class="muted-note">${fmt.esc(inst.error || d.error)}</div>` : ""}`;
    const remote = S.where === "remote" ? `<div><div class="vs-label">Indirizzo dell'altro computer</div>
        <div class="vs-row"><input type="text" id="vs-url" placeholder="http://192.168.1.20:3900" value="${fmt.esc(S.url)}" autocomplete="off"></div></div>
      <div><div class="vs-label">Chiave dello Studio</div>
        <div class="vs-row"><input type="password" id="vs-key" placeholder="${d.has_key ? "Chiave salvata: incollane una nuova per cambiarla" : "Incolla qui la chiave (OMNIVOICE_API_KEY)"}" value="${fmt.esc(S.key)}" autocomplete="off">
        <button type="button" class="btn" id="vs-check">Verifica</button></div><div class="vs-msg" id="vs-check-msg"></div></div>` : "";
    return `<div class="muted-note">Lo Studio delle voci è un programma a parte che Atena usa per parlare con voci nuove. Scegli dove deve funzionare e premi il pulsante.</div>
      <div><div class="vs-label">Dove funziona</div><div class="vs-cards">
        ${card("where", "local", "🖥", "Su questo computer", "Atena lo installa da sola. Serve un computer potente con 12 GB liberi.")}
        ${card("where", "remote", "💻", "Su un altro computer", "Hai già VoiceStudio su un altro PC di casa, magari con una scheda video.")}</div></div>
      ${remote}
      <div class="vs-row">${d.enabled ? `<button type="button" class="btn primary vs-big" id="vs-save">💾 Salva</button><button type="button" class="btn vs-big" id="vs-off">⏻ Spegni lo Studio</button>`
        : `<button type="button" class="btn primary vs-big" id="vs-on">⏻ Accendi lo Studio</button>`}</div>
      ${status}`;
  }

  function voicesHtml() {
    const d = S.data || {}, list = d.voices || [];
    if (!list.length) return `<div class="vs-empty">Non hai ancora creato nessuna voce.<br><br><button type="button" class="btn primary vs-big" data-goto="create">✨ Crea la prima voce</button></div>`;
    const studioMain = list.some((v) => v.id === d.atena_voice);
    return `<div class="muted-note">Premi «Ascolta» per sentirla e «Usa per Atena» per farla parlare con quella voce.</div>
      <div class="vs-voices">${list.map((v) => `<div class="vs-voice ${v.id === d.atena_voice ? "main" : ""}">
        <div class="vs-voice-name"><span>${v.id === d.atena_voice ? "⭐" : "🎙"}</span><b>${fmt.esc(v.name)}</b></div>
        <div class="vs-row"><button type="button" class="btn" data-play="${fmt.esc(v.id)}">▶ Ascolta</button>
          ${v.id === d.atena_voice ? `<span class="vs-msg ok">Voce di Atena</span>` : `<button type="button" class="btn primary" data-use="${fmt.esc(v.id)}">⭐ Usa per Atena</button>`}</div>
        <button type="button" class="btn danger" data-del="${fmt.esc(v.id)}">🗑 Elimina</button></div>`).join("")}</div>
      ${studioMain ? `<div class="vs-row"><button type="button" class="btn" data-use="">↩ Torna alla voce di prima</button></div>` : ""}`;
  }

  function render() {
    renderSteps();
    light();
    const s = STEPS.find((x) => x.id === S.step);
    const body = S.step === "power" ? powerHtml() : S.step === "voices" ? voicesHtml() : A.vsCreate.html();
    const i = STEPS.indexOf(s);
    $("vs-body").innerHTML = `<div class="panel-title" style="margin:0">${s.icon} ${fmt.esc(s.title)}</div>${body}
      <div class="vs-nav">${i ? '<button type="button" class="btn" data-go="-1">← Indietro</button>' : "<span></span>"}
        ${i < STEPS.length - 1 ? `<button type="button" class="btn primary" data-go="1" ${ready() ? "" : "disabled"}>Avanti →</button>` : ""}</div>`;
    $("vs-summary").textContent = STEPS.map((x) => summary(x.id)).join(" · ");
  }

  function schedule() {
    clearTimeout(S.timer);
    if (A.isOn("voicestudio") && S.data && S.data.enabled && !ready()) S.timer = setTimeout(load, 4000);
  }

  async function load() {
    try {
      S.data = await A.api("GET", "/api/voicestudio");
      if (!S.busy) { S.where = S.data.where; S.url = S.url || S.data.url; }
    } catch (e) { S.data = S.data || { enabled: false, voices: [] }; A.toast(e.message, true); }
    if (!ready() && S.step !== "power") S.step = "power";
    const typing = document.activeElement && /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName) && $("vs-body").contains(document.activeElement);
    if (!typing) render();
    schedule();
  }

  async function saveWhere() {
    const body = { ATENA_VOICESTUDIO_WHERE: S.where };
    if (S.where === "remote") {
      body.ATENA_VOICESTUDIO_URL = S.url.trim();
      if (S.key) body.ATENA_VOICESTUDIO_KEY = S.key;
    }
    await A.api("PUT", "/api/features/voicestudio/settings", body);
  }

  async function power(on) {
    S.busy = true;
    try {
      if (on) await saveWhere();
      await A.api("PUT", "/api/features/voicestudio", { mode: on ? "1" : "0" });
      A.toast(on ? "Accendo lo Studio delle voci" : "Studio delle voci spento");
      S.key = "";
    } catch (e) { A.toast(e.message, true); } finally { S.busy = false; }
    load();
  }

  async function check() {
    const msg = $("vs-check-msg");
    msg.textContent = "Verifico…"; msg.className = "vs-msg";
    try {
      const r = await A.api("POST", "/api/voicestudio/check", { url: S.url.trim(), key: S.key });
      msg.textContent = r.ok ? "✅ Collegamento riuscito" : `⚠ ${r.message}`; msg.className = `vs-msg ${r.ok ? "ok" : "bad"}`;
    } catch (e) { msg.textContent = e.message; msg.className = "vs-msg"; msg.classList.add("bad"); }
  }

  A.vsPlay = async (voice, btn, text) => {
    if (btn) btn.disabled = true;
    try {
      const r = await fetch("/api/voicestudio/preview", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-Atena-Request": "1" },
        body: JSON.stringify({ voice, text: text || "", language: (window.ATENA_UI_LANG || navigator.language || "it").slice(0, 2) }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Errore ${r.status}`);
      if (S.audio) S.audio.pause();
      S.audio = new Audio(URL.createObjectURL(await r.blob())); S.audio.play();
    } catch (e) { A.toast(e.message, true); } finally { if (btn) btn.disabled = false; }
  };
  A.vsReload = load;
  A.vsRender = render;

  async function onClick(e) {
    const t = e.target.closest("button");
    if (!t) return;
    if (t.dataset.set) { S[t.dataset.set] = t.dataset.value; return render(); }
    if (t.dataset.go) { const i = STEPS.findIndex((s) => s.id === S.step) + Number(t.dataset.go); S.step = STEPS[Math.max(0, Math.min(2, i))].id; return render(); }
    if (t.dataset.goto) { S.step = t.dataset.goto; return render(); }
    if (t.id === "vs-on") return power(true);
    if (t.id === "vs-off") return confirm("Spegnere lo Studio delle voci? Le voci create restano salvate.") && power(false);
    if (t.id === "vs-save") { try { await saveWhere(); A.toast("Impostazioni salvate"); S.key = ""; } catch (err) { A.toast(err.message, true); } return load(); }
    if (t.id === "vs-check") return check();
    if (t.id === "vs-retry") { try { await A.api("POST", "/api/voicestudio/retry"); A.toast("Riprovo l'installazione"); } catch (err) { A.toast(err.message, true); } return load(); }
    if (t.dataset.play) return A.vsPlay(t.dataset.play, t);
    try {
      if (t.dataset.use !== undefined) { await A.api("PUT", "/api/voicestudio/use", { voice: t.dataset.use }); A.toast(t.dataset.use ? "Ora Atena parla con questa voce" : "Atena è tornata alla voce di prima"); return load(); }
      if (t.dataset.del && confirm("Eliminare questa voce? Non si potrà recuperare.")) { await A.api("DELETE", `/api/voicestudio/voices/${encodeURIComponent(t.dataset.del)}`); A.toast("Voce eliminata"); return load(); }
    } catch (err) { A.toast(err.message, true); return undefined; }
    return A.vsCreate.click(t);
  }

  function init() {
    $("vs-steps").addEventListener("click", (e) => { const b = e.target.closest("[data-step]"); if (b && !b.disabled) { S.step = b.dataset.step; render(); } });
    $("vs-body").addEventListener("click", onClick);
    $("vs-body").addEventListener("input", (e) => {
      if (e.target.id === "vs-url") S.url = e.target.value;
      if (e.target.id === "vs-key") S.key = e.target.value.trim();
      A.vsCreate.input(e.target);
    });
    $("vs-body").addEventListener("change", (e) => A.vsCreate.change(e.target));
  }

  A.tab("voicestudio", { title: "Studio delle voci", init, load, leave: () => { clearTimeout(S.timer); A.vsCreate.stop(); } });
})();
