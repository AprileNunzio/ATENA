(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const C = A.cams;
  let selected = "";

  const enc = encodeURIComponent;

  function sourceOptions() {
    return C.data.sources.map((s) => `<option value="${C.esc(s.id)}" ${s.id === selected ? "selected" : ""}>${C.esc(s.name)} (${s.usage.photos} foto, ${s.usage.clips} clip)</option>`).join("");
  }

  function photoHtml(id, p) {
    return `<div class="cam-photo" data-name="${C.esc(p.name)}"><img src="/api/cameras/source/${enc(id)}/photos/${enc(p.name)}" loading="lazy" alt="Foto" data-act="open">
      <div class="cap"><span>${C.when(p.at)} · ${C.bytes(p.size)}</span><span><a href="/api/cameras/source/${enc(id)}/photos/${enc(p.name)}" download="${C.esc(p.name)}">⬇</a> <a href="#" data-act="del-photo">🗑</a></span></div></div>`;
  }

  function clipHtml(reg, c) {
    return `<div class="cam-row" data-name="${C.esc(c.name)}"><span>${C.when(c.at)} · ${C.bytes(c.size)}</span>
      <span><a class="btn sm" href="/api/cameras/clips/${enc(reg)}/${enc(c.name)}" download="${C.esc(c.name)}">Scarica</a> <button class="btn sm danger" data-act="del-clip">Elimina</button></span></div>`;
  }

  async function body() {
    const s = C.source(selected);
    if (!s) return '<div class="faint">Nessuna sorgente.</div>';
    const photos = (await A.api("GET", `/api/cameras/source/${enc(selected)}/photos`)).photos;
    let clips = [];
    if (s.record.id) clips = (await A.api("GET", `/api/cameras/clips/${enc(s.record.id)}`)).clips;
    return `<div class="panel-title">Foto</div>${photos.length ? `<div class="cam-photos">${photos.map((p) => photoHtml(selected, p)).join("")}</div>` : '<div class="faint">Nessuna foto. Scattane una con il pulsante qui sopra, dalla vista dal vivo o a voce.</div>'}
      <div class="panel-title" style="margin-top:18px">Clip registrate</div>${clips.length ? `<div class="cam-list">${clips.map((c) => clipHtml(s.record.id, c)).join("")}</div>` : '<div class="faint">Nessuna clip. La registrazione ad anello si attiva dalle opzioni della telecamera e conserva solo gli ultimi minuti scelti.</div>'}`;
  }

  async function paint() {
    if (!selected || !C.source(selected)) selected = (C.data.sources[0] || {}).id || "";
    const content = selected ? await body().catch((e) => `<div class="cam-err">${C.esc(e.message)}</div>`) : '<div class="faint">Nessuna sorgente.</div>';
    $("cam-pane-archive").innerHTML = `<div class="panel"><div class="cam-form"><div><label>Sorgente</label><select id="arc-src">${sourceOptions()}</select></div>
      <div class="cam-actions"><button class="btn primary" data-act="shot">📷 Scatta ora</button><button class="btn danger" data-act="purge">Svuota archivio</button></div></div>
      <div style="margin-top:14px">${content}</div></div>`;
  }

  async function onClick(e) {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const act = b.dataset.act, holder = b.closest("[data-name]");
    if (act === "open") { const box = $("cam-lightbox"); const img = document.createElement("img"); img.src = b.src; box.replaceChildren(img); box.hidden = false; return; }
    e.preventDefault();
    try {
      if (act === "shot") await C.photo(selected);
      else if (act === "del-photo") await A.api("DELETE", `/api/cameras/source/${enc(selected)}/photos/${enc(holder.dataset.name)}`);
      else if (act === "del-clip") await A.api("DELETE", `/api/cameras/clips/${enc(C.source(selected).record.id)}/${enc(holder.dataset.name)}`);
      else if (act === "purge") {
        if (!confirm("Cancellare tutte le foto e le clip di questa sorgente?")) return;
        const s = C.source(selected);
        for (const p of (await A.api("GET", `/api/cameras/source/${enc(selected)}/photos`)).photos) await A.api("DELETE", `/api/cameras/source/${enc(selected)}/photos/${enc(p.name)}`);
        if (s.record.id) for (const c of (await A.api("GET", `/api/cameras/clips/${enc(s.record.id)}`)).clips) await A.api("DELETE", `/api/cameras/clips/${enc(s.record.id)}/${enc(c.name)}`);
        A.toast("Archivio svuotato");
      }
    } catch (err) { A.toast(err.message, true); }
    await C.reload();
    paint();
  }

  function init() {
    const pane = $("cam-pane-archive");
    pane.addEventListener("click", onClick);
    pane.addEventListener("change", (e) => { if (e.target.id === "arc-src") { selected = e.target.value; paint(); } });
  }

  C.panes.archive = { init, load: paint };
})();
