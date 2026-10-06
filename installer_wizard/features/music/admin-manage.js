(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const mu = A.mu, esc = mu.esc;
  const M = mu.manage = {};
  let timer = null;

  const mb = (n) => (n >= 1073741824 ? `${(n / 1073741824).toFixed(1)} GB` : `${Math.round(n / 1048576)} MB`);
  const when = (s) => (s ? new Date(s * 1000).toLocaleString("it-IT") : "mai");

  async function section(id, fn) {
    try { $(id).innerHTML = await fn(); } catch (e) { $(id).textContent = e.message; }
  }

  async function library() {
    const c = await mu.loadConfig();
    const sv = c.service || {}, sc = sv.scan || {};
    const running = sc.running ? `<span class="badge running">scansione in corso: ${sc.done}/${sc.total}</span>` : '<span class="badge ok">a riposo</span>';
    return `<dl class="mu-kv"><dt>Brani</dt><dd>${c.tracks || 0} · ${c.albums || 0} album · ${c.artists || 0} artisti</dd><dt>Spazio</dt><dd>${mb(c.bytes || 0)} · ${mu.long(c.seconds || 0)}</dd>
      <dt>Cartella</dt><dd>${esc(c.root || "")}</dd><dt>Ultimo controllo</dt><dd>${when(sv.last)} ${running}</dd>
      <dt>Smistati</dt><dd>${(sv.organized || {}).moved || 0} brani · ${(sv.organized || {}).duplicates || 0} doppioni messi da parte</dd>
      <dt>Strumenti</dt><dd>${c.tags ? '<span class="badge ok">lettura dei tag</span>' : '<span class="badge warn">tag non leggibili: si usa il nome dei file</span>'} ${c.ffmpeg ? '<span class="badge ok">conversione formati</span>' : '<span class="badge warn">ffmpeg assente</span>'}</dd></dl>
      <div class="mu-actions"><button class="btn primary" data-m="scan">Controlla ora</button><button class="btn" data-m="full">Rilettura completa</button>
        <button class="btn" data-m="covers">Cerca copertine, dati e testi</button><button class="btn" data-m="identify">Riconosci i brani senza dati</button><button class="btn" data-m="names">Nomi completi dei file…</button><button class="btn" data-m="dups">Trova i doppioni</button><button class="btn" data-m="settings">Impostazioni</button></div><div id="mu-dups"></div>`;
  }

  function upload() {
    return `<div class="mu-drop" id="mu-drop">Trascina qui i brani oppure <label class="btn sm" style="display:inline-block;margin:0">scegli i file<input id="mu-files" type="file" multiple accept="audio/*,.flac,.m4a,.ogg,.opus,.wma,.aiff,.alac" hidden></label>
      <div class="mu-note">I file vanno in «Da smistare» e Atena li ordina da sola in Artista/Album. Puoi anche copiarli dalla rete nella cartella condivisa.</div><div id="mu-up"></div></div>`;
  }

  async function sendFiles(files) {
    const box = $("mu-up");
    for (const file of files) {
      const line = document.createElement("div");
      line.className = "mu-note";
      line.textContent = `${file.name}: invio…`;
      box.appendChild(line);
      try {
        const r = await fetch(`/api/music/upload?name=${encodeURIComponent(file.name)}`, { method: "PUT", headers: { "X-Atena-Request": "1" }, body: file, credentials: "same-origin" });
        const d = await r.json().catch(() => ({}));
        line.textContent = r.ok ? `${file.name}: caricato` : `${file.name}: ${d.detail || r.status}`;
      } catch (e) { line.textContent = `${file.name}: ${e.message}`; }
    }
    A.toast("Caricamento terminato: Atena sta smistando i brani");
    await mu.post("/api/music/scan", {}).then((r) => { const m = (r.result.sorted || {}).moved || 0; A.toast(m ? `${m} brani smistati` : "Brani ricevuti: li smisto appena la copia è finita"); }).catch((e) => console.info(e));
  }

  async function network() {
    const [shares, app] = await Promise.all([mu.get("/api/music/shares"), mu.get("/api/music/app")]);
    const host = location.hostname;
    const links = shares.shares.map((s) => `<tr><td>${esc({ track: "Brano", album: "Album", playlist: "Playlist" }[s.kind])}</td><td class="dim">scade ${when(s.expires)}</td><td class="dim">${s.uses} aperture</td>
      <td><button class="btn sm danger" data-revoke="${esc(s.token)}">Revoca</button></td></tr>`).join("");
    return `<dl class="mu-kv"><dt>Cartella di rete</dt><dd><code>\\\\${esc(host)}\\condivisa\\06 Musica</code> <button class="btn sm" data-m="copy-smb">Copia</button></dd>
      <dt>App per telefono</dt><dd>${app.enabled ? `<span class="badge ok">attivo</span>` : '<span class="badge">spento</span>'}</dd></dl>
      <p class="mu-note">Le app compatibili con Subsonic (per esempio Symfonium, DSub, Substreamer, Feishin) si collegano alla tua libreria: indirizzo <code>${esc(app.url)}</code>, utente a piacere, password qui sotto.</p>
      <div class="mu-actions"><button class="btn ${app.enabled ? "" : "primary"}" data-m="app-toggle">${app.enabled ? "Spegni il server per le app" : "Attiva il server per le app"}</button>
        ${app.enabled ? '<button class="btn" data-m="app-new">Nuova password</button>' : ""}</div>
      ${app.enabled && app.password ? `<dl class="mu-kv"><dt>Indirizzo</dt><dd><code>${esc(app.url)}</code></dd><dt>Password</dt><dd><code id="mu-app-pass" data-pass="${esc(app.password)}">••••••••••••</code>
        <button class="btn sm" data-m="app-show">Mostra</button> <button class="btn sm" data-m="app-copy">Copia</button></dd></dl>` : ""}
      <h3>Link condivisi attivi</h3>${links ? `<table class="mu-table"><tbody>${links}</tbody></table>` : '<div class="mu-note">Nessun link attivo. Dal menu «⋯» di un brano, album o playlist puoi crearne uno.</div>'}`;
  }

  async function ambient() {
    const m = await mu.get("/api/music");
    const np = m.now_playing || {};
    const step = m.step || {};
    const state = !m.enabled ? '<span class="badge">spento</span>' : step.status === "failed" ? '<span class="badge down">errore</span>' : m.installed ? '<span class="badge ok">attivo</span>' : '<span class="badge warn">installazione…</span>';
    return `<div class="mu-actions"><label class="switch"><input type="checkbox" id="mu-amb" ${m.enabled ? "checked" : ""}> Riconosci la musica che suona nella stanza</label>${state}</div>
      ${np.title ? `<div class="mu-dev"><div class="ic">♪</div><div class="nm"><b>${esc(np.title)}</b><small>${esc([np.artist, np.album, np.year].filter(Boolean).join(" · "))}</small></div>
        <button class="btn sm" data-search="${esc(np.title)}">Cerca nella libreria</button></div>` : '<div class="mu-note">Nessun brano riconosciuto in questo momento.</div>'}
      <p class="mu-note">Quando in stanza suona musica per almeno dieci secondi, Atena la riconosce dall'impronta acustica e la mostra sul display. Da spento l'audio non lascia mai la macchina.</p>`;
  }

  let waiting = [];

  async function unassigned() {
    waiting = (await mu.get("/api/music/unassigned")).files;
    if (!waiting.length) return '<div class="mu-note">Nessun brano in attesa: Atena riconosce e smista tutto da sola.</div>';
    return `<p class="mu-note">Questi brani non hanno un artista e non sono riuscito a riconoscerli. Restano in «Da smistare» finché non decidi tu: dai un nome e un artista, oppure mettili nei Mix.</p>
      ${waiting.map((f, i) => `<div class="mu-dev"><div class="ic">♪</div><div class="nm"><b>${esc(f.title || f.name)}</b><small>${esc(f.name)}</small></div>
        <button class="btn sm primary" data-assign="${i}">Assegna…</button><button class="btn sm" data-mix="${i}">Nei Mix</button></div>`).join("")}`;
  }

  function assign(i) {
    const f = waiting[i];
    const row = (key, label, type = "text") => `<label>${label}<input data-f="${key}" type="${type}" value="${esc(f[key])}"></label>`;
    mu.modal("Assegna il brano", `<div class="mu-form">${row("title", "Titolo")}${row("artist", "Artista")}${row("album", "Album (vuoto = Singoli)")}${row("year", "Anno", "number")}${row("genre", "Genere")}${row("track_no", "Numero traccia", "number")}</div>`, async (wrap) => {
      const body = { path: f.path };
      wrap.querySelectorAll("[data-f]").forEach((el) => { body[el.dataset.f] = el.value.trim(); });
      if (!body.artist) { A.toast("Serve almeno l'artista", true); return false; }
      const r = await mu.post("/api/music/assign", body);
      A.toast(`Assegnato: ${(r.result.sorted || {}).moved || 0} brani smistati`);
      section("mu-s-un", unassigned);
      section("mu-s-lib", library);
      return true;
    }, "Assegna e smista");
  }

  async function toMix(i) {
    const f = waiting[i];
    await mu.post("/api/music/assign", { path: f.path, mix: true, title: f.title });
    A.toast("Messo nei Mix");
    section("mu-s-un", unassigned);
    section("mu-s-lib", library);
  }

  async function dups() {
    const r = await mu.get("/api/music/duplicates");
    $("mu-dups").innerHTML = r.duplicates.length ? r.duplicates.map((d) => `<div class="mu-dev"><div class="nm"><b>${esc(d.title)}</b><small>${esc(d.artist)} · ${d.copies} copie</small>
      ${d.files.map((f) => `<small>${esc(f.path)} · ${f.bitrate || "?"} kbps · ${mb(f.size)} <button class="btn sm danger" data-trash="${f.id}">Cestino</button></small>`).join("")}</div></div>`).join("")
      : '<div class="mu-note">Nessun doppione: ogni brano compare una volta sola.</div>';
  }

  mu.views.manage = async () => {
    $("mu-main").innerHTML = `<h2>Gestione e condivisione</h2>
      <div class="grid g2"><div class="panel"><div class="panel-title">Libreria</div><div id="mu-s-lib">…</div></div>
        <div class="panel"><div class="panel-title">Aggiungi musica</div>${upload()}</div>
        <div class="panel"><div class="panel-title">Da assegnare</div><div id="mu-s-un">…</div></div>
        <div class="panel"><div class="panel-title">Condivisione in rete</div><div id="mu-s-net">…</div></div>
        <div class="panel"><div class="panel-title">Riconoscimento ambientale</div><div id="mu-s-amb">…</div></div></div>`;
    section("mu-s-lib", library); section("mu-s-un", unassigned); section("mu-s-net", network); section("mu-s-amb", ambient);
    clearInterval(timer);
    timer = setInterval(() => { if (A.isOn("music") && mu.view.name === "manage") section("mu-s-lib", library); else clearInterval(timer); }, 5000);
    const drop = $("mu-drop");
    ["dragover", "dragenter"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", (e) => sendFiles([...e.dataTransfer.files]));
    $("mu-files").addEventListener("change", (e) => sendFiles([...e.target.files]));
  };

  async function scan(full) {
    A.toast("Controllo la libreria…");
    const r = (await mu.post("/api/music/scan", { full })).result;
    const s = r.sorted || {}, c = r.scan || {};
    const parts = [];
    if (s.moved) parts.push(`${s.moved} brani smistati`);
    if (s.duplicates) parts.push(`${s.duplicates} doppioni messi da parte`);
    if (s.fixed) parts.push(`${s.fixed} brani rimessi in ordine`);
    if (s.waiting) parts.push(`${s.waiting} ancora in copia`);
    if (c.added) parts.push(`${c.added} aggiunti alla libreria`);
    A.toast(parts.length ? parts.join(", ") : "Niente di nuovo da smistare");
    (r.errors || []).forEach((e) => A.toast(`Non smistato: ${e}`, true));
    section("mu-s-lib", library);
  }

  async function identifyNow() {
    A.toast("Ascolto i brani senza dati… può volerci un po'");
    const r = await mu.post("/api/music/identify");
    if (!r.available) { A.toast("Il riconoscimento dal suono non è installato su questo server", true); return; }
    A.toast(r.tried ? `Riconosciuti ${r.identified} brani su ${r.tried}, rinominati ${r.renamed}` : "Tutti i brani hanno già i loro dati");
    (r.items || []).forEach((i) => A.toast(`${i.file} → ${[i.artist, i.title, i.album, i.year].filter(Boolean).join(" · ")}`));
    section("mu-s-lib", library);
  }

  async function names() {
    const p = await mu.get("/api/music/rename/preview");
    if (!p.total) { A.toast("Tutti i file hanno già un nome completo"); return; }
    mu.modal(`Nomi completi: ${p.total} file`, `<p class="mu-note">Formato: numero - artista - titolo (anno). Ecco i primi cambiamenti:</p>
      <div class="mu-scroll">${p.steps.map((s) => `<div class="mu-note"><b>${esc(s.from.split("/").pop())}</b><br>→ ${esc(s.to.replace(/^Libreria\//, ""))}</div>`).join("")}</div>`, async () => {
      const r = await mu.post("/api/music/rename");
      A.toast(`Rinominati ${r.renamed} file${r.failed ? `, ${r.failed} non rinominati` : ""}`);
      section("mu-s-lib", library);
    }, "Applica");
  }

  const actions = {
    scan: () => scan(false),
    identify: identifyNow,
    names,
    full: () => scan(true),
    covers: async () => { A.toast("Cerco copertine, dati e testi…"); const r = await mu.post("/api/music/covers/complete"); A.toast(`Copertine e dati trovati: ${r.saved}, testi salvati: ${r.lyrics}`); },
    dups,
    settings: () => A.openFeature("music"),
    "copy-smb": () => A.copy(`\\\\${location.hostname}\\condivisa\\06 Musica`, "percorso di rete"),
    "app-toggle": async () => { const a = await mu.get("/api/music/app"); await mu.post("/api/music/app", { enabled: !a.enabled }); section("mu-s-net", network); },
    "app-new": async () => { if (confirm("Generare una nuova password? Le app collegate dovranno aggiornarla.")) { await mu.post("/api/music/app", { enabled: true, regenerate: true }); section("mu-s-net", network); } },
    "app-show": () => { const el = $("mu-app-pass"); el.textContent = el.textContent.startsWith("•") ? el.dataset.pass : "••••••••••••"; },
    "app-copy": () => A.copy($("mu-app-pass").dataset.pass, "password", true),
  };

  async function click(e) {
    const el = e.target.closest("[data-m], [data-revoke], [data-trash], [data-search], [data-assign], [data-mix]");
    if (!el) return;
    try {
      if (el.dataset.m && actions[el.dataset.m]) await actions[el.dataset.m]();
      else if (el.dataset.revoke) { await mu.post(`/api/music/shares/${encodeURIComponent(el.dataset.revoke)}/revoke`); section("mu-s-net", network); }
      else if (el.dataset.trash) { if (confirm("Spostare questa copia nel cestino della libreria?")) { await mu.post(`/api/music/tracks/${el.dataset.trash}/trash`); dups(); } }
      else if (el.dataset.assign !== undefined) assign(Number(el.dataset.assign));
      else if (el.dataset.mix !== undefined) await toMix(Number(el.dataset.mix));
      else if (el.dataset.search) { mu.searchText = el.dataset.search; mu.go("search"); }
    } catch (err) { mu.err(err); }
  }

  async function change(e) {
    if (e.target.id !== "mu-amb") return;
    try {
      await A.api("PUT", "/api/music", { enabled: e.target.checked });
      A.toast(e.target.checked ? "Riconoscimento attivato" : "Riconoscimento disattivato");
      section("mu-s-amb", ambient);
    } catch (err) { mu.err(err); }
  }

  M.init = () => {
    $("mu-main").addEventListener("click", click);
    $("mu-main").addEventListener("change", change);
  };
})();
