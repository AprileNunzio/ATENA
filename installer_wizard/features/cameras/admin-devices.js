(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const C = A.cams;
  let irTimer = null, lastIr = false, sessionTimer = null;

  const badge = (text, kind = "") => `<span class="badge ${kind}">${fmt.esc(text)}</span>`;
  const mode = (m) => (m ? `${m.width}x${m.height}${m.fps ? ` · ${Math.round(m.fps)} fps` : ""}` : "?");

  const IR_TEXT = {
    ok: ["ok", "Infrarosso attivo: il flusso arriva e ha luce"],
    dark: ["warn", "Infrarosso aperto ma al buio: l'emettitore non è acceso (vedi sotto)"],
    no_frames: ["warn", "Nessun fotogramma dal sensore infrarosso"],
    absent: ["", "Nessun sensore infrarosso in uso"],
  };

  function sessionHtml(e, run) {
    if (run.running) {
      return `<div class="bio-note">Configurazione in corso (${run.elapsed || 0} s). Guarda l'emettitore sulla webcam: quando lampeggia rispondi Sì, altrimenti No.</div>
        <pre class="bio-term" id="bio-term">${fmt.esc(run.output || "…")}</pre>
        <div class="bio-line"><button class="btn sm primary" data-bio="answer-y">Sì, lampeggia</button>
        <button class="btn sm" data-bio="answer-n">No</button><button class="btn sm" data-bio="cancel">Interrompi</button></div>`;
    }
    const last = run.result ? `<div class="bio-note">Ultima configurazione: ${fmt.esc(run.result)}</div>${run.output ? `<pre class="bio-term">${fmt.esc(run.output)}</pre>` : ""}` : "";
    return `<div class="bio-note">Atena può guidare la configurazione da qui: mette in pausa la visione, prova i comandi della webcam e ti chiede se l'emettitore lampeggia. Prova controlli della webcam e in rari casi può alterarne le impostazioni.</div>
      <div class="bio-line"><button class="btn sm primary" data-bio="configure">Configura l'emettitore</button></div>${last}
      <div class="bio-note">In alternativa sul server: <span class="bio-cmd">${fmt.esc(e.command)} <button class="btn sm" data-copy-cmd="${fmt.esc(e.command)}">Copia</button></span></div>`;
  }

  function autoHtml(e) {
    const a = e.auto || {};
    if (a.running) {
      return `<div class="bio-note">Configurazione automatica: ${fmt.esc(a.stage || "…")}</div>
        <pre class="bio-term" id="bio-term">${fmt.esc((e.session || {}).output || "…")}</pre>
        <div class="bio-line"><button class="btn sm" data-bio="cancel">Interrompi</button></div>`;
    }
    const last = a.result ? `<div class="bio-note">Ultimo esito: ${fmt.esc(a.result)}</div>` : "";
    const go = e.supported_arch && !e.service
      ? '<div class="bio-line"><button class="btn sm primary" data-bio="auto">Configura tutto in automatico</button></div><div class="bio-note">Installa lo strumento, trova da solo il nodo infrarosso giusto, prova le combinazioni, verifica dai fotogrammi che la luce sia accesa e la rende permanente. Nessuna risposta richiesta.</div>'
      : "";
    return go + last;
  }

  function emitterHtml(e, ir) {
    if (!e) return "";
    if ((e.auto || {}).running) return autoHtml(e);
    const state = [
      badge(e.tool ? `strumento ${e.version} installato` : "strumento non installato", e.tool ? "ok" : ""),
      badge(e.configured ? "emettitore configurato" : "emettitore da configurare", e.configured ? "ok" : "warn"),
      badge(e.service ? "attivo a ogni avvio" : "non attivo all'avvio", e.service ? "ok" : ""),
    ].join(" ");
    const install = !e.tool && e.supported_arch
      ? '<button class="btn sm" data-bio="install">Installa lo strumento</button>' : "";
    const enable = e.tool && e.configured && !e.service ? '<button class="btn sm primary" data-bio="enable">Attiva a ogni avvio</button>' : "";
    const run = e.session || {};
    const guide = e.tool && !e.configured ? sessionHtml(e, run) : "";
    const dark = ir && ir.state === "dark" && !e.tool ? '<div class="bio-note">Se la luce infrarossa non si accende da sola, serve lo strumento per attivare l\'emettitore.</div>' : "";
    return `<div class="bio-line">${state}</div>${dark}${autoHtml(e)}<div class="bio-line">${install}${enable}</div>${guide}
      ${e.last ? `<div class="bio-note">${fmt.esc(e.last)}</div>` : ""}`;
  }

  function camsHtml(d) {
    const sel = (d.selected || {}).device;
    const devices = (d.devices || []).map((c) => `<div class="bio-dev"><b>${fmt.esc(c.name)}</b>
      <div class="bio-line">${c.id === sel ? badge("in uso", "ok") : ""}
        ${c.rgb ? badge(`colori ${mode(c.rgb_mode)}`) : ""}
        ${c.has_ir ? badge(`infrarossi ${mode(c.ir_mode)}`, "ok") : badge("senza infrarossi")}
        ${badge(c.driver || "driver standard")}</div></div>`).join("");
    const ir = d.ir_status || {};
    const [kind, text] = IR_TEXT[ir.state] || IR_TEXT.absent;
    const hasIr = (d.devices || []).some((c) => c.has_ir) || ir.state === "ok" || ir.state === "dark";
    const problems = (d.problems || []).map((p) => `<div class="bio-note" style="color:var(--amber)">${fmt.esc(p)}</div>`).join("");
    const tools = d.tools && d.tools["v4l2-ctl"] === false ? '<div class="bio-note" style="color:var(--amber)">v4l-utils non è installato: lo installa l\'aggiornamento del servizio Visione.</div>' : "";
    return `<div class="bio-line"><button class="btn sm" data-bio="rescan">Riesamina le webcam</button></div>${devices || '<div class="faint">Nessuna webcam rilevata. Collegane una: viene riconosciuta da sola, senza riavviare.</div>'}
      ${problems}${tools}
      ${hasIr ? `<div class="bio-line">${badge(text, kind)}</div>${d.emitter ? emitterHtml(d.emitter, ir) : ""}
      <img class="bio-ir" id="bio-ir" alt="Immagine infrarossa" hidden>` : ""}`;
  }

  function refreshIr() {
    const img = $("bio-ir");
    if (!img || !A.isOn("people")) return;
    img.hidden = false;
    img.onerror = () => { img.hidden = true; };
    img.src = `/api/vision/ir.jpg?t=${Date.now()}`;
  }

  async function loadCams() {
    let d;
    try { d = await A.api("GET", "/api/vision/webcams"); } catch (e) { $("cam-pane-devices").textContent = e.message; return; }
    $("cam-pane-devices").innerHTML = camsHtml(d);
    if ($("bio-term") && !sessionTimer) watchSession();
    lastIr = !!$("bio-ir");
    clearInterval(irTimer);
    if (lastIr) { refreshIr(); irTimer = setInterval(refreshIr, 2500); }
  }

  async function act(kind) {
    try {
      if (kind === "install") {
        if (!confirm("Installare lo strumento che accende l'emettitore infrarosso? Viene scaricata la versione verificata con impronta SHA-256. La successiva configurazione prova i controlli della webcam e può alterarne le impostazioni: procedi solo se accetti il rischio.")) return;
        A.toast("Download in corso…");
        await A.api("POST", "/api/vision/webcams/ir/install", { confirm: true });
        A.toast("Strumento installato");
      } else if (kind === "configure") {
        if (!confirm("Avviare la configurazione guidata? La visione viene messa in pausa e la webcam infrarossa riceve comandi di prova: procedi solo se accetti il rischio.")) return;
        await A.api("POST", "/api/vision/webcams/ir/configure", { confirm: true });
        A.toast("Configurazione avviata");
        watchSession();
      } else if (kind === "auto") {
        if (!confirm("Configurare l'emettitore infrarosso in automatico? Atena installa lo strumento verificato, mette in pausa la visione e prova comandi sulla webcam infrarossa finché la luce si accende. In rari casi può alterare le impostazioni della webcam: procedi solo se accetti il rischio.")) return;
        await A.api("POST", "/api/vision/webcams/ir/auto", { confirm: true });
        A.toast("Configurazione automatica avviata");
        watchSession();
      } else if (kind === "answer-y" || kind === "answer-n") {
        await A.api("POST", "/api/vision/webcams/ir/configure/answer", { answer: kind.slice(-1) });
      } else if (kind === "cancel") {
        await A.api("POST", "/api/vision/webcams/ir/configure/cancel");
      } else if (kind === "enable") {
        await A.api("POST", "/api/vision/webcams/ir/enable");
        A.toast("Emettitore attivato a ogni avvio");
      } else if (kind === "rescan") {
        await A.api("POST", "/api/vision/webcams/rescan");
        A.toast("Webcam riesaminate");
      }
    } catch (e) { A.toast(e.message, true); }
    loadCams();
  }

    function watchSession() {
    clearInterval(sessionTimer);
    sessionTimer = setInterval(async () => {
      await loadCams();
      const term = $("bio-term");
      if (!term) { clearInterval(sessionTimer); sessionTimer = null; } else term.scrollTop = term.scrollHeight;
    }, 1500);
  }

  function init() {
    $("cam-pane-devices").addEventListener("click", (e) => {
      const b = e.target.closest("[data-bio]");
      if (b) return act(b.dataset.bio);
      const c = e.target.closest("[data-copy-cmd]");
      if (c) A.copy(c.dataset.copyCmd);
    });
  }

  function leave() { clearInterval(irTimer); clearInterval(sessionTimer); sessionTimer = null; }

  C.panes.devices = { init, load: loadCams, leave };
})();
