(() => {
  const A = window.AtenaAdmin, { fmt } = A;
  const VIEWS = [
    { kind: "front", icon: "🙂", label: "Frontale", hint: "Guarda dritto la webcam" },
    { kind: "three_left", icon: "↖", label: "Tre quarti sinistra", hint: "Gira un poco la testa verso la tua sinistra" },
    { kind: "three_right", icon: "↗", label: "Tre quarti destra", hint: "Gira un poco la testa verso la tua destra" },
    { kind: "left", icon: "⬅", label: "Profilo sinistro", hint: "Gira la testa del tutto verso la tua sinistra" },
    { kind: "right", icon: "➡", label: "Profilo destro", hint: "Gira la testa del tutto verso la tua destra" },
    { kind: "up", icon: "⬆", label: "Testa alta", hint: "Alza leggermente il mento" },
    { kind: "down", icon: "⬇", label: "Testa bassa", hint: "Abbassa leggermente il mento" },
    { kind: "body", icon: "🧍", label: "Corpo intero", hint: "Allontanati finché la webcam ti inquadra dalla testa ai piedi" },
    { kind: "body_back", icon: "🔙", label: "Corpo di spalle", hint: "Allontanati e girati di spalle" },
  ];
  const LABEL = Object.fromEntries(VIEWS.map((v) => [v.kind, v.label]));
  const MAX_SIDE = 1600;
  let photos = [], views = {}, current = null;

  async function load(slug) {
    const [p, v] = await Promise.all([
      A.api("GET", `/api/people/${encodeURIComponent(slug)}/photos`),
      A.api("GET", `/api/people/${encodeURIComponent(slug)}/views`),
    ]);
    photos = p.photos || [];
    views = v.views || {};
  }

  function panel() {
    const done = VIEWS.filter((v) => views[v.kind]).length, pct = Math.round((done / VIEWS.length) * 100);
    return `
      <div class="views-panel">
        <div class="views-head">
          <div>
            <div class="views-title">Vista a 360°</div>
            <div class="gallery-summary-text">Più angolazioni del viso e del corpo rendono il riconoscimento affidabile anche di profilo,
              da lontano e con luce diversa. Scatta dalla webcam seguendo l'indicazione oppure carica foto già fatte.</div>
          </div>
          <div class="views-score"><b>${pct}%</b><span>${done} di ${VIEWS.length} viste</span></div>
        </div>
        <div class="views-grid">
          ${VIEWS.map((v) => `
            <div class="view-cell ${views[v.kind] ? "done" : ""}">
              <div class="view-icon">${v.icon}</div>
              <div class="view-label">${fmt.esc(v.label)}</div>
              <div class="view-count">${views[v.kind] ? `✓ ${views[v.kind]} foto` : "mancante"}</div>
              <div class="view-actions">
                <button class="btn sm" data-view-capture="${v.kind}" title="${fmt.esc(v.hint)}">📷 Webcam</button>
                <label class="btn sm view-upload">⬆ Carica<input type="file" accept="image/*" multiple hidden data-view-upload="${v.kind}"></label>
              </div>
            </div>`).join("")}
        </div>
        <div class="row" style="gap:10px; margin-top:12px; flex-wrap:wrap">
          <label class="btn primary view-upload">⬆ Carica più foto (angolazione riconosciuta da sola)<input type="file" accept="image/*" multiple hidden data-view-upload="auto"></label>
          <span class="muted-note" id="views-progress"></span>
        </div>
      </div>`;
  }

  function grid() {
    if (!photos.length) {
      return '<div class="muted-note" style="grid-column:1/-1;">Nessuna foto memorizzata. Inizia dalla vista frontale qui sopra.</div>';
    }
    return photos.map((ph) => `
      <div class="gallery-photo-card ${ph.is_primary ? "is-primary" : ""}">
        <img class="gallery-photo-img ${String(ph.kind || "").startsWith("body") ? "is-body" : ""}" src="${fmt.esc(ph.url)}" loading="lazy">
        <div class="gallery-photo-meta">
          ${ph.is_primary ? '<span class="primary-tag">⭐ Viso Frontale Principale</span>'
            : `<span class="muted-note">${fmt.esc(LABEL[ph.kind] || "Campione Angolazione / Luce")}</span>`}
          <button class="btn sm danger btn-delete-photo" data-photo-id="${fmt.esc(ph.id)}" title="Elimina questa foto se errata">🗑 Elimina Foto</button>
        </div>
      </div>`).join("");
  }

  function section(p) {
    const qPct = p.quality_pct || 0;
    return `
      <div class="gallery-section-box">
        <div class="gallery-controls-bar">
          <div>
            <div style="font-weight:600; font-size:14px; margin-bottom:4px;">Galleria Foto Riconoscimento Biometrico</div>
            <div class="gallery-summary-text">
              Tutte le migliori foto utilizzate dal motore di riconoscimento per questa persona.
              La notte, il sistema automatico perfeziona il modello biometrico. Se rilevi foto errate o mal associate, puoi eliminarle e riprogettare il riconoscimento.
            </div>
          </div>
          <div class="row" style="gap:10px;">
            <button class="btn primary" id="btn-reproject" title="Ricalcola e ottimizza il modello biometrico per questa persona">🔄 Riprogetta Riconoscimento</button>
          </div>
        </div>
        ${panel()}
        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
          <div style="font-size:13px; font-weight:500;">Foto Campione (${photos.length})</div>
          <div style="font-size:12px; color:var(--text-dim);">Accuratezza attuale: <b style="color:var(--cyan);">${qPct}%</b></div>
        </div>
        <div class="gallery-photos-grid">${grid()}</div>
      </div>`;
  }

  async function shrink(file) {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, MAX_SIDE / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * k); canvas.height = Math.round(bmp.height * k);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close();
    return new Promise((ok, ko) => canvas.toBlob((b) => (b ? ok(b) : ko(new Error("Conversione della foto non riuscita"))), "image/jpeg", 0.9));
  }

  async function upload(slug, kind, file) {
    const body = await shrink(file);
    const r = await fetch(`/api/people/${encodeURIComponent(slug)}/views?kind=${encodeURIComponent(kind)}`, {
      method: "POST", credentials: "same-origin", body,
      headers: { "X-Atena-Request": "1", "Content-Type": "image/jpeg" },
    });
    if (r.status === 401) { A.showLogin(); throw new Error("Sessione scaduta"); }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `Errore ${r.status}`);
    return data;
  }

  async function uploadAll(input) {
    if (!current) return;
    const files = [...input.files], kind = input.dataset.viewUpload, note = document.getElementById("views-progress");
    input.value = "";
    let ok = 0;
    const failed = [];
    for (const [i, file] of files.entries()) {
      if (note) note.textContent = `Analisi foto ${i + 1} di ${files.length}…`;
      try {
        const r = await upload(current.slug, kind, file);
        ok += 1;
        if (kind === "auto") A.toast(`${file.name}: ${r.label}${r.face ? "" : " (senza volto)"}`);
      } catch (err) {
        failed.push(`${file.name}: ${err.message}`);
      }
    }
    if (note) note.textContent = "";
    failed.forEach((msg) => A.toast(msg, true));
    if (ok) { A.toast(`${ok} foto aggiunte alla galleria`); current.reload(); }
  }

  async function capture(t, slug) {
    const v = VIEWS.find((x) => x.kind === t.dataset.viewCapture);
    if (!v) return;
    const text = t.textContent;
    t.disabled = true; t.textContent = "3 secondi…";
    A.toast(`${v.hint}: resta fermo per 3 secondi davanti alla webcam`);
    try {
      const r = await A.api("POST", `/api/people/${encodeURIComponent(slug)}/views/capture?kind=${v.kind}`);
      A.toast(`${v.label} acquisita (${r.samples} campioni in totale)`);
      current.reload();
    } finally {
      t.disabled = false; t.textContent = text;
    }
  }

  async function handle(t, slug, reload) {
    current = { slug, reload };
    if (t.dataset.viewCapture) { await capture(t, slug); return true; }
    if (t.id === "btn-reproject") {
      t.disabled = true; t.textContent = "Riprogettazione in corso…";
      try {
        const res = await A.api("POST", `/api/people/${encodeURIComponent(slug)}/reproject`);
        A.toast(`Riconoscimento riprogettato con successo! Nuova qualità: ${res.quality_pct}%`);
        reload();
      } finally {
        t.disabled = false; t.textContent = "🔄 Riprogetta Riconoscimento";
      }
      return true;
    }
    if (t.classList.contains("btn-delete-photo")) {
      const photoId = t.dataset.photoId;
      if (!photoId || !confirm("Rimuovere questa foto dal modello di riconoscimento?")) return true;
      await A.api("DELETE", `/api/people/${encodeURIComponent(slug)}/photos/${encodeURIComponent(photoId)}`);
      A.toast("Foto rimossa con successo");
      reload();
      return true;
    }
    return false;
  }

  document.addEventListener("change", (e) => {
    const input = e.target;
    if (input && input.dataset && input.dataset.viewUpload) uploadAll(input).catch((err) => A.toast(err.message, true));
  });

  A.PeopleGallery = {
    load, section, handle,
    bind(slug, reload) { current = { slug, reload }; },
    clear() { photos = []; views = {}; },
  };
})();
