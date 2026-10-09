(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const LANGS = [["it", "🇮🇹 Italiano"], ["en", "🇬🇧 English"], ["fr", "🇫🇷 Français"], ["es", "🇪🇸 Español"], ["de", "🇩🇪 Deutsch"], ["pt", "🇵🇹 Português"]];
  const GROUPS = [["gender", "Chi parla?"], ["age", "Quanti anni ha?"], ["pitch", "Che tono ha?"], ["style", "Come parla?"]];
  const MAX_SECONDS = 30;
  const C = { mode: "design", name: "", picks: { style: "" }, lang: (window.ATENA_UI_LANG || navigator.language || "it").slice(0, 2), consent: false,
    blob: null, file: "", recorder: null, stream: null, seconds: 0, tick: null, sending: false };
  if (!LANGS.some(([v]) => v === C.lang)) C.lang = "it";

  const canRecord = () => !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  const sentence = () => ((A.vs.data && A.vs.data.sentences) || {})[C.lang] || "";
  const nameOk = () => /^[\p{L}\p{N} '.-]{1,40}$/u.test(C.name.trim());

  function tiles(group) {
    const options = ((A.vs.data && A.vs.data.choices) || {})[group] || [];
    return `<div class="vs-tiles">${options.map((o) => `<button type="button" class="vs-tile ${(C.picks[group] ?? "") === o.value ? "on" : ""}" data-pick="${group}" data-value="${fmt.esc(o.value)}">
      <span>${o.icon}</span>${fmt.esc(o.title)}</button>`).join("")}</div>`;
  }

  function designHtml() {
    const ready = nameOk() && ["gender", "age", "pitch", "style"].some((g) => C.picks[g]);
    return `${GROUPS.map(([g, label]) => `<div><div class="vs-label">${fmt.esc(label)}</div>${tiles(g)}</div>`).join("")}
      <div class="vs-row"><button type="button" class="btn primary vs-big" id="vs-make" ${ready && !C.sending ? "" : "disabled"}>${C.sending ? "⏳ Sto creando la voce…" : "✨ Crea la voce"}</button></div>`;
  }

  function cloneHtml() {
    const text = sentence().replace("{name}", C.name.trim() || "…");
    const ready = nameOk() && C.consent && C.blob && !C.sending;
    const recorder = canRecord()
      ? `<div class="vs-row"><button type="button" class="vs-rec ${C.recorder ? "on" : ""}" id="vs-rec" title="${C.recorder ? "Ferma" : "Registra"}">${C.recorder ? "⏹" : "🔴"}</button>
          <span class="vs-timer">${C.seconds}s</span><span class="muted-note">${C.recorder ? "Leggi la frase ad alta voce, poi premi ⏹" : C.blob ? "Registrazione pronta" : "Premi il pallino rosso e leggi la frase"}</span>
          ${C.blob && !C.recorder ? '<button type="button" class="btn" id="vs-listen">▶ Riascolta</button><button type="button" class="btn" id="vs-again">🔁 Rifai</button>' : ""}</div>`
      : `<div class="vs-msg bad">Questo browser non può registrare qui: scegli un file audio con la frase letta.</div>`;
    return `<div><div class="vs-label">Lingua della frase</div><div class="vs-row"><select id="vs-lang">${LANGS.map(([v, l]) => `<option value="${v}" ${v === C.lang ? "selected" : ""}>${l}</option>`).join("")}</select></div></div>
      <label class="vs-consent"><input type="checkbox" id="vs-consent" ${C.consent ? "checked" : ""}><span>La persona di cui copio la voce è d'accordo e leggerà lei la frase. Se sei tu, va benissimo.</span></label>
      <div><div class="vs-label">Leggi questa frase con calma</div><div class="vs-sentence" id="vs-sentence">${fmt.esc(text)}</div></div>
      ${recorder}
      <div class="vs-row"><label class="btn">📁 Oppure scegli un file audio<input type="file" id="vs-file" accept="audio/*,video/webm" hidden></label>${C.file ? `<span class="muted-note">${fmt.esc(C.file)}</span>` : ""}</div>
      <div class="vs-row"><button type="button" class="btn primary vs-big" id="vs-make" ${ready ? "" : "disabled"}>${C.sending ? "⏳ Sto imparando la voce…" : "✨ Crea la voce"}</button></div>`;
  }

  function html() {
    const tab = (mode, icon, title, text) => `<button type="button" class="vs-card ${C.mode === mode ? "on" : ""}" data-mode="${mode}">
      <span class="vs-ic">${icon}</span><b>${fmt.esc(title)}</b><small>${fmt.esc(text)}</small></button>`;
    return `<div class="vs-cards">${tab("design", "🎨", "Inventa una voce", "Scegli com'è fatta con le figure")}
        ${tab("clone", "🎤", "Copia una voce", "Leggi una frase e Atena impara quella voce")}</div>
      <div><div class="vs-label">Come si chiama la voce?</div><div class="vs-row"><input type="text" id="vs-name" maxlength="40" placeholder="Per esempio: Nonno Pino" value="${fmt.esc(C.name)}" autocomplete="off"></div></div>
      ${C.mode === "design" ? designHtml() : cloneHtml()}`;
  }

  function stop() {
    if (C.recorder && C.recorder.state !== "inactive") C.recorder.stop();
    if (C.stream) C.stream.getTracks().forEach((t) => t.stop());
    clearInterval(C.tick);
    C.recorder = null; C.stream = null;
  }

  async function record() {
    if (C.recorder) { stop(); return; }
    try {
      C.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) { A.toast("Non posso usare il microfono: controlla i permessi del browser", true); return; }
    const parts = [];
    C.recorder = new MediaRecorder(C.stream);
    C.recorder.ondataavailable = (ev) => { if (ev.data.size) parts.push(ev.data); };
    C.recorder.onstop = () => { C.blob = new Blob(parts, { type: C.recorder ? C.recorder.mimeType : "audio/webm" }); C.file = ""; A.vsRender(); };
    C.recorder.start();
    C.seconds = 0; C.blob = null;
    C.tick = setInterval(() => { C.seconds += 1; if (C.seconds >= MAX_SECONDS) stop(); A.vsRender(); }, 1000);
    A.vsRender();
  }

  async function make(btn) {
    C.sending = true; A.vsRender();
    try {
      let voice;
      if (C.mode === "design") {
        const r = await A.api("POST", "/api/voicestudio/design", { name: C.name.trim(), language: C.lang, ...C.picks });
        voice = r.voice;
      } else {
        const form = new FormData();
        form.append("name", C.name.trim()); form.append("language", C.lang); form.append("consent", C.consent ? "1" : "0");
        form.append("audio", C.blob, C.file || "registrazione.webm");
        const res = await fetch("/api/voicestudio/clone", { method: "POST", credentials: "same-origin", headers: { "X-Atena-Request": "1" }, body: form });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Errore ${res.status}`);
        voice = data.voice;
      }
      A.toast(`Voce «${C.name.trim()}» creata!`);
      Object.assign(C, { name: "", picks: { style: "" }, blob: null, file: "", consent: false, seconds: 0 });
      A.vs.step = "voices";
      await A.vsReload();
      if (voice) A.vsPlay(voice, btn);
    } catch (e) { A.toast(e.message, true); } finally { C.sending = false; A.vsRender(); }
  }

  A.vsCreate = {
    html,
    stop,
    click(t) {
      if (t.dataset.mode) { C.mode = t.dataset.mode; stop(); return A.vsRender(); }
      if (t.dataset.pick) { C.picks[t.dataset.pick] = C.picks[t.dataset.pick] === t.dataset.value && t.dataset.pick !== "style" ? "" : t.dataset.value; return A.vsRender(); }
      if (t.id === "vs-rec") return record();
      if (t.id === "vs-again") { C.blob = null; C.seconds = 0; return A.vsRender(); }
      if (t.id === "vs-listen" && C.blob) { new Audio(URL.createObjectURL(C.blob)).play(); return undefined; }
      if (t.id === "vs-make") return make(t);
      return undefined;
    },
    input(el) {
      if (el.id !== "vs-name") return;
      C.name = el.value;
      const make = $("vs-make");
      if (make) make.disabled = !nameOk() || C.sending || (C.mode === "clone" ? !(C.consent && C.blob) : !["gender", "age", "pitch", "style"].some((g) => C.picks[g]));
      const box = $("vs-sentence");
      if (box) box.textContent = sentence().replace("{name}", C.name.trim() || "…");
    },
    change(el) {
      if (el.id === "vs-lang") { C.lang = el.value; A.vsRender(); }
      if (el.id === "vs-consent") { C.consent = el.checked; A.vsRender(); }
      if (el.id === "vs-file" && el.files[0]) {
        const f = el.files[0];
        if (f.size > 25 * 1024 * 1024) { A.toast("File troppo grande (massimo 25 MB)", true); return; }
        stop(); C.blob = f; C.file = f.name; C.seconds = 0; A.vsRender();
      }
    },
  };
})();
