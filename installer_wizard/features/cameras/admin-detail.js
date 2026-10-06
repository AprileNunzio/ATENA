(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const C = A.cams;
  let current = null;

  const opt = (value, label, sel) => `<option value="${value}" ${String(sel) === String(value) ? "selected" : ""}>${label}</option>`;
  const check = (f, label, on, extra = "") => `<label class="switch"><input type="checkbox" data-f="${f}" ${on ? "checked" : ""} ${extra}> ${label}</label>`;

  function optionsHtml(s) {
    const o = s.options;
    const stream = s.stream ? `<div><label>Fluidità</label><select data-f="fps">${opt(0, "Predefinita", o.fps)}${[5, 8, 12, 20, 25].map((v) => opt(v, `${v} al secondo`, o.fps)).join("")}</select></div>
      <div><label>Larghezza</label><select data-f="width">${opt(0, "Predefinita", o.width)}${[320, 480, 640, 960, 1280, 1920].map((v) => opt(v, `${v} px`, o.width)).join("")}</select></div>` : "";
    return `<div class="panel-title">Aspetto e nome</div><div class="cam-form">
      <div><label>Nome</label><input type="text" data-f="alias" maxlength="40" value="${C.esc(o.alias)}" placeholder="${C.esc(s.name)}"></div>
      <div><label>Stanza</label><input type="text" data-f="room" maxlength="40" value="${C.esc(o.room)}" placeholder="Es. salotto"></div>
      <div><label>Rotazione</label><select data-f="rotate">${[0, 90, 180, 270].map((v) => opt(v, `${v}°`, o.rotate)).join("")}</select></div>
      <div>${check("mirror", "Specchio orizzontale", o.mirror)}</div>${stream}
      <div>${check("favorite", "Preferita (in cima)", o.favorite)}</div><div>${check("hidden", "Nascosta a display e voce", o.hidden)}</div></div>`;
  }

  function motionHtml(s) {
    const o = s.options;
    return `<div class="panel-title" style="margin-top:18px">Avviso di movimento</div><div class="cam-form">
      <div>${check("motion", "Avvisami se si muove qualcosa", o.motion)}</div>
      <div><label>Sensibilità: <b id="cam-sens">${o.sensitivity}</b> / 10</label><div class="cam-range"><span class="faint">bassa</span><input type="range" min="1" max="10" data-f="sensitivity" value="${o.sensitivity}"><span class="faint">alta</span></div></div>
      <div class="wide">${check("photo_on_motion", "Scatta anche una foto quando rileva movimento", o.photo_on_motion)}</div></div>
      <div class="bio-note">Confronta due immagini piccole ogni pochi secondi, non conserva nulla. Le foto al movimento vanno nell'archivio.</div>`;
  }

  function recordHtml(s) {
    const r = s.record;
    if (!r.available) return `<div class="panel-title" style="margin-top:18px">Registrazione</div><div class="bio-note">${C.esc(r.reason)}</div>`;
    return `<div class="panel-title" style="margin-top:18px">Registrazione ad anello</div><div class="cam-form" data-record>
      <div>${check("enabled", "Attiva", r.enabled)}</div><div>${check("consent", "Consenso a riprendere", r.consent)}</div><div>${check("record", "Registra", r.record)}</div>
      <div><label>Anello</label><select data-r="retention_min">${[5, 15, 60].map((m) => opt(m, m === 60 ? "1 ora" : `${m} minuti`, r.retention_min)).join("")}</select></div></div>
      ${r.record && r.enabled && !r.consent ? '<div class="cam-warn">Serve il consenso per registrare.</div>' : ""}
      ${r.recording ? '<div class="cam-err">● Sta registrando ora</div>' : ""}`;
  }

  function usageHtml(s) {
    const u = s.usage;
    return `<div class="bio-note" style="margin-top:14px">Archivio: ${u.photos} foto (${C.bytes(u.photo_bytes)}), ${u.clips} clip (${C.bytes(u.clip_bytes)}).</div>`;
  }

  async function controlsHtml(s) {
    if (!s.controllable) return "";
    let d;
    try { d = await A.api("GET", `/api/cameras/source/${encodeURIComponent(s.id)}/controls`); } catch (e) { return `<div class="bio-note">Controlli non disponibili: ${C.esc(e.message)}</div>`; }
    const rows = d.controls.filter((c) => !c.inactive).map((c) => {
      const label = c.name.replace(/_/g, " ");
      if (c.type === "bool") return `<div>${check("ctl", label, c.value === 1, `data-name="${c.name}" data-bool`)}</div>`;
      if (c.type === "menu") return `<div><label>${C.esc(label)}</label><select data-ctl data-name="${c.name}">${c.menu.map((m) => opt(m.value, C.esc(m.label), c.value)).join("")}</select></div>`;
      return `<div><label>${C.esc(label)}: <b>${c.value}</b></label><div class="cam-range"><input type="range" data-ctl data-name="${c.name}" min="${c.min}" max="${c.max}" step="${c.step}" value="${c.value}"><span class="faint">${c.default}</span></div></div>`;
    });
    return `<div class="panel-title" style="margin-top:18px">Controlli della webcam</div>${rows.length ? `<div class="cam-form">${rows.join("")}</div>
      <div class="cam-actions" style="margin-top:10px"><button class="btn sm" data-act="reset-ctl">Ripristina valori di fabbrica</button></div>
      <div class="bio-note">I valori vengono ricordati e riapplicati a ogni avvio o collegamento.</div>` : '<div class="bio-note">Nessun controllo disponibile.</div>'}`;
  }

  async function paint(s) {
    $("cam-drawer").innerHTML = `<div class="bio-line" style="justify-content:space-between"><div class="panel-title" style="margin:0">${C.esc(s.name)}</div><button class="btn sm" data-act="close">Chiudi</button></div>
      <div class="bio-line">${C.badge(C.kind(s))}${s.main ? C.badge("in uso dalla visione", "ok") : ""}</div>
      ${optionsHtml(s)}${s.kind === "infrared" ? "" : motionHtml(s)}${recordHtml(s)}${usageHtml(s)}${await controlsHtml(s)}
      <div class="cam-actions" style="margin-top:18px"><button class="btn sm" data-act="photo">📷 Scatta una foto</button><button class="btn sm danger" data-act="remove">${s.kind === "ip" ? "Elimina telecamera" : "Dimentica impostazioni e archivio"}</button></div>`;
  }

  async function open(id) {
    current = id;
    const s = C.source(id);
    if (!s) return;
    $("cam-drawer").hidden = false;
    await paint(s);
  }

  const put = (path, body) => A.api("PUT", `/api/cameras/source/${encodeURIComponent(current)}/${path}`, body);

  async function refresh() {
    await C.reload();
    const s = C.source(current);
    if (s && !$("cam-drawer").hidden) await paint(s);
    if (C.pane === "live") C.renderLive();
  }

  async function onChange(e) {
    const t = e.target;
    try {
      if (t.dataset.ctl !== undefined || t.dataset.bool !== undefined) {
        const value = t.type === "checkbox" ? (t.checked ? 1 : 0) : parseInt(t.value, 10);
        await put("controls", { name: t.dataset.name, value });
        return;
      }
      if (t.dataset.r) { await put("record", { [t.dataset.r]: parseInt(t.value, 10) }); return refresh(); }
      if (t.closest("[data-record]")) { await put("record", { [t.dataset.f]: t.checked }); return refresh(); }
      if (!t.dataset.f) return;
      const num = ["rotate", "fps", "width", "sensitivity"].includes(t.dataset.f);
      const value = t.type === "checkbox" ? t.checked : num ? parseInt(t.value, 10) : t.value.trim();
      await put("options", { [t.dataset.f]: value });
      await refresh();
    } catch (err) { A.toast(err.message, true); refresh(); }
  }

  async function onClick(e) {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const act = b.dataset.act;
    try {
      if (act === "close") { $("cam-drawer").hidden = true; current = null; }
      else if (act === "photo") await C.photo(current);
      else if (act === "reset-ctl") {
        if (!confirm("Riportare i controlli della webcam ai valori di fabbrica?")) return;
        await A.api("POST", `/api/cameras/source/${encodeURIComponent(current)}/controls/reset`);
        A.toast("Valori ripristinati");
        await refresh();
      } else if (act === "remove") {
        if (!confirm("Eliminare impostazioni, foto e clip di questa sorgente? Le telecamere di rete vengono rimosse e la registrazione si ferma.")) return;
        await A.api("DELETE", `/api/cameras/source/${encodeURIComponent(current)}`);
        $("cam-drawer").hidden = true; current = null;
        await refresh();
      }
    } catch (err) { A.toast(err.message, true); }
  }

  function init() {
    const d = $("cam-drawer");
    d.addEventListener("change", onChange);
    d.addEventListener("click", onClick);
    d.addEventListener("input", (e) => { if (e.target.dataset.f === "sensitivity") $("cam-sens").textContent = e.target.value; });
  }

  function leave() { $("cam-drawer").hidden = true; current = null; }

  C.panes.detail = { open, init, leave };
})();
