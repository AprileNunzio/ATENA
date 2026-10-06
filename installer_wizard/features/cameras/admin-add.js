(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const C = A.cams;
  let brands = [];

  const field = (id, label, input, wide = false) => `<div${wide ? ' class="wide"' : ""}><label for="${id}">${label}</label>${input}</div>`;

  function html() {
    const brandOptions = brands.map((b) => `<option value="${C.esc(b.id)}">${C.esc(b.label)}</option>`).join("");
    return `<div class="panel" style="margin-bottom:16px"><div class="panel-title">Trova telecamere nella rete</div>
        <div class="bio-note">Cerca le telecamere ONVIF e chi ha la porta RTSP aperta nella tua rete locale. Contatta solo indirizzi privati (fino a 256).</div>
        <div class="cam-form" style="margin-top:10px">${field("cam-net", "Rete (vuoto = la tua)", '<input type="text" id="cam-net" placeholder="192.168.1.0/24" maxlength="20">')}
        <div><button class="btn primary" id="cam-discover">Cerca in rete</button></div></div>
        <div id="cam-found" class="cam-list" style="margin-top:10px"></div></div>
      <div class="panel"><div class="panel-title">Aggiungi una telecamera</div>
        <form class="cam-form" id="cam-add-form" autocomplete="off">
          ${field("cam-kind", "Tipo", '<select id="cam-kind"><option value="rtsp">Telecamera di rete (RTSP)</option><option value="onvif">ONVIF</option><option value="hikvision">Hikvision</option></select>')}
          ${field("cam-name", "Nome", '<input type="text" id="cam-name" maxlength="60" placeholder="Es. Ingresso">')}
          ${field("cam-room", "Stanza", '<input type="text" id="cam-room" maxlength="40" placeholder="Es. giardino">')}
          <div class="wide"><div class="panel-title" style="margin:6px 0">Modello per marca (compila l'indirizzo per te)</div></div>
          ${field("cam-brand", "Marca", `<select id="cam-brand">${brandOptions}</select>`)}
          ${field("cam-host", "Indirizzo IP", '<input type="text" id="cam-host" placeholder="192.168.1.50" maxlength="80">')}
          ${field("cam-port", "Porta (0 = predefinita)", '<input type="number" id="cam-port" min="0" max="65535" value="0">')}
          ${field("cam-user", "Utente", '<input type="text" id="cam-user" maxlength="60" autocomplete="off">')}
          ${field("cam-pass", "Password", '<input type="password" id="cam-pass" maxlength="80" autocomplete="new-password">')}
          ${field("cam-chan", "Canale", '<input type="number" id="cam-chan" min="1" max="32" value="1">')}
          ${field("cam-stream", "Qualità", '<select id="cam-stream"><option value="main">Principale (alta)</option><option value="sub">Secondaria (leggera)</option></select>')}
          <div class="wide"><button type="button" class="btn" id="cam-build">Genera indirizzo</button></div>
          ${field("cam-url", "Indirizzo del flusso", '<input type="text" id="cam-url" maxlength="300" placeholder="rtsp://utente:password@192.168.1.50:554/stream1">', true)}
          ${field("cam-ret", "Anello di registrazione", '<select id="cam-ret"><option value="5">5 minuti</option><option value="15">15 minuti</option><option value="60">1 ora</option></select>')}
          <div class="wide cam-actions"><button type="button" class="btn" id="cam-test">Prova la connessione</button><button class="btn primary">Aggiungi</button></div>
          <div class="wide" id="cam-test-out"></div>
        </form></div>`;
  }

  function foundRow(r) {
    const label = [r.name, r.host, r.onvif ? "ONVIF" : "", r.ports.length ? `RTSP ${r.ports.join(", ")}` : ""].filter(Boolean).join(" · ");
    return `<div class="cam-row"><span>${C.esc(label)}${r.known ? " " + C.badge("già aggiunta", "ok") : ""}</span><button class="btn sm" data-use="${C.esc(r.host)}" data-name="${C.esc(r.name)}">Usa</button></div>`;
  }

  async function discover() {
    if (!confirm("Cercare telecamere nella rete locale? Vengono contattati gli indirizzi della rete per controllare le porte RTSP e gli annunci ONVIF.")) return;
    const box = $("cam-found");
    box.innerHTML = '<div class="faint">Ricerca in corso (qualche secondo)…</div>';
    try {
      const d = await A.api("POST", "/api/cameras/discover", { confirm: true, network: $("cam-net").value.trim() });
      box.innerHTML = d.found.length ? `<div class="bio-note">Rete ${C.esc(d.network)}: ${d.found.length} trovate</div>${d.found.map(foundRow).join("")}`
        : `<div class="faint">Nessuna telecamera trovata in ${C.esc(d.network)}. Se è accesa ma non appare, aggiungila a mano con il suo indirizzo.</div>`;
    } catch (e) { box.innerHTML = `<div class="cam-err">${C.esc(e.message)}</div>`; }
  }

  async function build() {
    try {
      const r = await A.api("POST", "/api/cameras/presets/build", { brand: $("cam-brand").value, host: $("cam-host").value.trim(), user: $("cam-user").value,
        password: $("cam-pass").value, channel: parseInt($("cam-chan").value, 10) || 1, stream: $("cam-stream").value, port: parseInt($("cam-port").value, 10) || 0 });
      $("cam-url").value = r.url;
    } catch (e) { A.toast(e.message, true); }
  }

  async function test() {
    const out = $("cam-test-out"), url = $("cam-url").value.trim();
    if (!url) { out.innerHTML = '<div class="cam-warn">Genera o scrivi prima l\'indirizzo del flusso.</div>'; return; }
    out.innerHTML = '<div class="faint">Prova in corso…</div>';
    try {
      const r = await A.api("POST", "/api/cameras/probe", { url });
      out.innerHTML = r.ok ? `<div class="cam-ok">✓ Funziona: ${r.width && r.height ? `${r.width}×${r.height}, ` : ""}risposta in ${r.ms} ms</div>`
        : `<div class="cam-err">✗ ${C.esc(r.error)}${r.hint ? ` — ${C.esc(r.hint)}` : ""}</div>`;
    } catch (e) { out.innerHTML = `<div class="cam-err">${C.esc(e.message)}</div>`; }
  }

  async function add(e) {
    e.preventDefault();
    const body = { name: $("cam-name").value.trim(), kind: $("cam-kind").value, url: $("cam-url").value.trim(), retention_min: parseInt($("cam-ret").value, 10) };
    if (!body.name || !body.url) { A.toast("Servono nome e indirizzo del flusso", true); return; }
    try {
      const cam = await A.api("POST", "/api/cameras", body);
      const room = $("cam-room").value.trim();
      if (room) await A.api("PUT", `/api/cameras/source/c-${encodeURIComponent(cam.id)}/options`, { room });
      A.toast("Telecamera aggiunta");
      ["cam-name", "cam-url", "cam-user", "cam-pass", "cam-room"].forEach((id) => { $(id).value = ""; });
      C.show("live");
    } catch (err) { A.toast(err.message, true); }
  }

  async function load() {
    if (!brands.length) { try { brands = (await A.api("GET", "/api/cameras/presets")).brands; } catch (e) { A.toast(e.message, true); } }
    if ($("cam-add-form")) return;
    $("cam-pane-add").innerHTML = html();
    $("cam-discover").addEventListener("click", discover);
    $("cam-build").addEventListener("click", build);
    $("cam-test").addEventListener("click", test);
    $("cam-add-form").addEventListener("submit", add);
    $("cam-found").addEventListener("click", (e) => {
      const b = e.target.closest("[data-use]");
      if (!b) return;
      $("cam-host").value = b.dataset.use;
      if (b.dataset.name && !$("cam-name").value) $("cam-name").value = b.dataset.name;
      $("cam-user").focus();
    });
  }

  C.panes.add = { load };
})();
