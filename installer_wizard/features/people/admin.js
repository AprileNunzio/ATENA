(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const DAYS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
  const initials = (n) => (n || "?").split(/\s+/).map((x) => x[0]).join("").slice(0, 2).toUpperCase();
  const avatar = (p, size = 64) => `<img class="frontal-avatar" style="width:${size}px;height:${size}px" src="/api/vision/people/${encodeURIComponent(p.slug)}/photo.jpg" onerror="this.outerHTML='<div class=&quot;frontal-avatar&quot; style=&quot;width:${size}px;height:${size}px;display:grid;place-items:center;font-size:${Math.round(size/2.5)}px;color:var(--cyan);background:rgba(2,8,16,0.8);&quot;>${fmt.esc(initials(p.name))}</div>'">`;
  const ago = (t) => t ? `${fmt.duration(Date.now() / 1000 - t)} fa` : "mai";

  let peopleData = { people: [], roles: {} }, peopleSchema = null;
  let currentPerson = null, currentSection = "identity";
  let personCache = null, peopleFilter = "", personPhotos = [];
  const saveTimers = {};

  function qualityClass(pct) {
    if (pct >= 80) return "high";
    if (pct >= 55) return "mid";
    return "low";
  }

  function qualityBoxHtml(pct) {
    const qPct = Math.max(5, Math.min(100, Math.round(pct || 75)));
    const cls = qualityClass(qPct);
    return `
      <div class="quality-box">
        <div class="quality-header">
          <span class="quality-label">Qualità Riconoscimento</span>
          <span class="quality-pct ${cls}">${qPct}%</span>
        </div>
        <div class="quality-progress">
          <div class="quality-progress-fill ${cls}" style="width:${qPct}%"></div>
        </div>
      </div>
    `;
  }

  async function loadPeople() {
    try {
      if (!peopleSchema) peopleSchema = await A.api("GET", "/api/people/schema");
      peopleData = await A.api("GET", "/api/people");
    } catch (e) {
      A.toast(e.message, true);
      return;
    }
    renderTwoSections();
    if (currentPerson) {
      openPerson(currentPerson);
    } else {
      showOverview();
    }
  }

  function showOverview() {
    currentPerson = null;
    const ov = $("people-overview");
    const det = $("person-detail-view");
    if (ov) ov.style.display = "flex";
    if (det) det.style.display = "none";
  }

  function showDetail() {
    const ov = $("people-overview");
    const det = $("person-detail-view");
    if (ov) ov.style.display = "none";
    if (det) det.style.display = "block";
  }

  function renderTwoSections() {
    const s = A.state;
    const present = new Set(((s && s.presence && s.presence.people) || []).filter((p) => p.known).map((p) => p.slug));
    const q = peopleFilter.toLowerCase().trim();

    const all = (peopleData.people || []).filter((p) =>
      !q || JSON.stringify([p.name, p.nickname, p.tags, p.occupation, p.role]).toLowerCase().includes(q)
    );

    const registered = all.filter((p) => !p.is_scanned);
    
    // Ordina alfabeticamente per cognome e nome se presenti
    registered.sort((a, b) => {
      const nameA = (a.last_name && a.first_name) ? `${a.last_name} ${a.first_name}` : (a.name || "");
      const nameB = (b.last_name && b.first_name) ? `${b.last_name} ${b.first_name}` : (b.name || "");
      return nameA.toLowerCase().localeCompare(nameB.toLowerCase());
    });

    const scanned = all.filter((p) => p.is_scanned);

    if ($("count-registered")) $("count-registered").textContent = `${registered.length} persone`;
    if ($("count-scanned")) $("count-scanned").textContent = `${scanned.length} volti`;

    // 1. Persone Registrate
    const regGrid = $("registered-grid");
    if (regGrid) {
      if (!registered.length) {
        regGrid.innerHTML = '<div class="muted-note" style="grid-column:1/-1;">Nessuna persona registrata trovata.</div>';
      } else {
        regGrid.innerHTML = registered.map((p) => {
          const displayName = (p.last_name && p.first_name) ? `${p.last_name} ${p.first_name}` : p.name;
          const isPres = present.has(p.slug);
          const age = p.computed && p.computed.age != null ? ` · ${p.computed.age} anni` : "";
          const roleLabel = peopleData.roles[p.role] || p.role || "Ospite";
          return `
            <div class="person-card" data-slug="${fmt.esc(p.slug)}">
              <div class="person-card-top">
                ${avatar(p, 64)}
                <div class="person-card-info">
                  <div class="person-card-name">${fmt.esc(displayName)}</div>
                  <div class="person-card-role">${fmt.esc(roleLabel)}${age}</div>
                  ${isPres ? '<span class="present">● presente ora</span>' : `<span class="muted-note" style="font-size:11px;">visto ${ago(p.stats && p.stats.last_seen)}</span>`}
                </div>
              </div>
              ${qualityBoxHtml(p.quality_pct)}
              <div class="person-card-actions">
                <button class="btn sm primary card-open-btn" data-open="${fmt.esc(p.slug)}">Visualizza Scheda</button>
              </div>
            </div>
          `;
        }).join("");
      }
    }

    // 2. Persone Scansionate
    const scnGrid = $("scanned-grid");
    if (scnGrid) {
      if (!scanned.length) {
        scnGrid.innerHTML = '<div class="muted-note" style="grid-column:1/-1;">Nessun volto scansionato da associare al momento. I volti rilevati dalla telecamera appariranno qui.</div>';
      } else {
        const regOptions = registered.map((rp) => {
          const displayAssocName = (rp.last_name && rp.first_name) ? `${rp.last_name} ${rp.first_name}` : rp.name;
          return `<option value="${fmt.esc(rp.slug)}">${fmt.esc(displayAssocName)}</option>`;
        }).join("");
        scnGrid.innerHTML = scanned.map((p) => {
          return `
            <div class="person-card" data-scanned-slug="${fmt.esc(p.slug)}" style="border-color:rgba(245,158,11,0.25);">
              <div class="person-card-top">
                ${avatar(p, 64)}
                <div class="person-card-info">
                  <div class="person-card-name" style="color:var(--amber);">${fmt.esc(p.name || "Volto Rilevato")}</div>
                  <div class="person-card-role">Scansione senza nome</div>
                  <span class="muted-note" style="font-size:11px;">visto ${ago(p.stats && p.stats.last_seen)}</span>
                </div>
              </div>
              ${qualityBoxHtml(p.quality_pct)}
              <div class="person-card-actions">
                <!-- Azione 1: Assegna un nome -->
                <div class="scanned-assign-box">
                  <input type="text" class="scanned-assign-input" placeholder="Assegna un nome…" data-input-slug="${fmt.esc(p.slug)}" maxlength="40">
                  <button class="btn sm primary btn-assign-name" data-slug="${fmt.esc(p.slug)}">Salva</button>
                </div>
                <!-- Azione 2: Associa a persona registrata -->
                <div class="scanned-assoc-box">
                  <select class="scanned-assoc-select" data-select-slug="${fmt.esc(p.slug)}">
                    <option value="">Associa a persona…</option>
                    ${regOptions}
                  </select>
                  <button class="btn sm btn-do-assoc" data-slug="${fmt.esc(p.slug)}">Associa</button>
                </div>
              </div>
            </div>
          `;
        }).join("");
      }
    }
  }

  function fieldInput(f, value, path) {
    const v = value ?? "";
    const attrs = `data-path="${fmt.esc(path)}" data-type="${f.type}"`;
    switch (f.type) {
      case "textarea": return `<textarea ${attrs} rows="3" placeholder="${fmt.esc(f.placeholder || "")}">${fmt.esc(v)}</textarea>`;
      case "bool": return `<label class="row" style="margin:0;gap:8px"><input type="checkbox" ${attrs} style="width:auto" ${v ? "checked" : ""}> ${fmt.esc(f.label)}</label>`;
      case "select": return `<select ${attrs}>${(f.options || []).map((o) => `<option value="${fmt.esc(o)}" ${o === v ? "selected" : ""}>${fmt.esc((f.labels && f.labels[o]) || o || "—")}</option>`).join("")}</select>`;
      case "tags": return `<input ${attrs} value="${fmt.esc(Array.isArray(v) ? v.join(", ") : v)}" placeholder="separati da virgola">`;
      case "person": return `<select ${attrs}><option value="">—</option>${peopleData.people.filter((p) => p.slug !== currentPerson).map((p) => `<option value="${fmt.esc(p.slug)}" ${p.slug === v ? "selected" : ""}>${fmt.esc(p.name)}</option>`).join("")}</select>`;
      default: return `<input ${attrs} type="${{ date: "date", number: "number", email: "email", tel: "tel", url: "url" }[f.type] || "text"}" value="${fmt.esc(v)}" placeholder="${fmt.esc(f.placeholder || "")}">`;
    }
  }

  function listRow(f, row, i) {
    return `<div class="list-row" data-row="${i}">${f.fields.map((sf) => sf.type === "bool"
      ? `<div>${fieldInput(sf, row[sf.key], `${f.key}.${i}.${sf.key}`)}</div>`
      : `<div><label>${fmt.esc(sf.label)}</label>${fieldInput(sf, row[sf.key], `${f.key}.${i}.${sf.key}`)}</div>`).join("")}
      <button class="btn sm danger" data-del="${f.key}" data-idx="${i}" title="Rimuovi">✕</button></div>`;
  }

  function renderField(f, p) {
    if (f.type === "list") {
      const rows = p[f.key] || [];
      return `<div class="list-field wide" data-list="${f.key}"><label>${fmt.esc(f.label)}</label>
        ${rows.map((row, i) => listRow(f, row, i)).join("")}
        <button class="btn sm" data-add="${f.key}">+ Aggiungi</button></div>`;
    }
    const extra = f.key === "name_day" && p.computed && p.computed.name_day_auto ? ` <span class="faint">(automatico: ${p.computed.name_day})</span>` : "";
    return f.type === "bool" ? `<div>${fieldInput(f, p[f.key], f.key)}</div>`
      : `<div class="${f.type === "textarea" ? "wide" : ""}"><label>${fmt.esc(f.label)}${extra}</label>${fieldInput(f, p[f.key], f.key)}</div>`;
  }

  async function loadPersonPhotos(slug) {
    try {
      const res = await A.api("GET", `/api/people/${encodeURIComponent(slug)}/photos`);
      personPhotos = res.photos || [];
    } catch (e) {
      personPhotos = [];
    }
  }

  function gallerySection(p) {
    const qPct = p.quality_pct || 75;
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
            <button class="btn" id="enroll-cam">📷 Nuova Foto da Webcam</button>
          </div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
          <div style="font-size:13px; font-weight:500;">Foto Campione (${personPhotos.length})</div>
          <div style="font-size:12px; color:var(--text-dim);">Accuratezza attuale: <b style="color:var(--cyan);">${qPct}%</b></div>
        </div>

        <div class="gallery-photos-grid">
          ${personPhotos.length ? personPhotos.map((ph) => `
            <div class="gallery-photo-card ${ph.is_primary ? "is-primary" : ""}">
              <img class="gallery-photo-img" src="${fmt.esc(ph.url)}" loading="lazy">
              <div class="gallery-photo-meta">
                ${ph.is_primary ? '<span class="primary-tag">⭐ Viso Frontale Principale</span>' : '<span class="muted-note">Campione Angolazione / Luce</span>'}
                <button class="btn sm danger btn-delete-photo" data-photo-id="${fmt.esc(ph.id)}" title="Elimina questa foto se errata">🗑 Elimina Foto</button>
              </div>
            </div>
          `).join("") : '<div class="muted-note" style="grid-column:1/-1;">Nessuna foto memorizzata. Cattura una foto frontale con la webcam per potenziare il riconoscimento.</div>'}
        </div>
      </div>
    `;
  }

  function voiceSection(p) {
    const vp = p.voiceprint || {};
    const vs = vp.enrolled ? `✓ registrata (${vp.samples} campioni${vp.updated ? `, ultimo ${new Date(vp.updated * 1000).toLocaleDateString("it-IT")}` : ""})`
      : vp.samples ? `in corso: ${vp.samples} campioni raccolti` : "non ancora registrata — dì «Atena, impara la mia voce» davanti alla webcam";
    return `<div class="form-grid">
        <div><label>Voce di Atena per questa persona</label><select data-voice="tts_voice"><option value="">Predefinita di sistema</option>
          ${Object.entries(peopleSchema.voices || {}).map(([v, label]) => `<option value="${v}" ${p.voice && p.voice.tts_voice === v ? "selected" : ""}>${fmt.esc(label)}</option>`).join("")}</select></div>
        <div><label>Velocità (${(p.voice && p.voice.speed) || 1.0})</label><input data-voice="speed" type="range" min="0.7" max="1.4" step="0.05" value="${(p.voice && p.voice.speed) || 1}"></div>
        <div><label>Tono (${(p.voice && p.voice.pitch) || 0})</label><input data-voice="pitch" type="range" min="-6" max="6" step="0.5" value="${(p.voice && p.voice.pitch) || 0}"></div>
        <div><label>Volume (${(p.voice && p.voice.volume) || 1.0})</label><input data-voice="volume" type="range" min="0.5" max="1.8" step="0.05" value="${(p.voice && p.voice.volume) || 1}"></div></div>
        <div class="row" style="justify-content:space-between; align-items:center; margin-top:14px">
          <div class="muted-note">Impronta vocale: ${vs}.</div>
          ${vp.enrolled || vp.samples ? '<button class="btn sm danger" id="forget-voice">Cancella impronta vocale</button>' : ""}</div>`;
  }

  function habitsSection(p) {
    const h = p.habits || { arrival_hours: [0]*24, weekdays: [0]*7, summary: "Nessuna abitudine registrata." };
    const maxH = Math.max(1, ...(h.arrival_hours || [1]));
    const maxD = Math.max(1, ...(h.weekdays || [1]));
    return `<div style="font-size:14px; margin-bottom:14px">${fmt.esc(h.summary)}</div>
        <div class="grid g2"><div><label>Orari di arrivo</label><div class="chart">${(h.arrival_hours || []).map((v) => `<i style="height:${(v / maxH) * 100}%" title="${v}"></i>`).join("")}</div><div class="chart-lbl"><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div></div>
        <div><label>Giorni della settimana</label><div class="chart">${(h.weekdays || []).map((v) => `<i style="height:${(v / maxD) * 100}%" title="${v}"></i>`).join("")}</div><div class="chart-lbl">${DAYS.map((d) => `<span>${d}</span>`).join("")}</div></div></div>
        <div class="muted-note">${p.stats ? p.stats.visits : 0} visite · ${fmt.duration(p.stats ? p.stats.total_seconds : 0)} di presenza · prima volta ${p.stats && p.stats.first_seen ? new Date(p.stats.first_seen * 1000).toLocaleDateString("it-IT") : "—"}</div>`;
  }

  function sectionHtml(p) {
    if (currentSection === "gallery") return gallerySection(p);
    if (currentSection === "voice") return voiceSection(p);
    if (currentSection === "habits") return habitsSection(p);
    const sec = peopleSchema.sections.find((s) => s.id === currentSection);
    if (!sec) return "";
    return `${sec.private ? '<div class="muted-note" style="margin:0 0 14px">🔒 Dati riservati: restano solo su questo dispositivo.</div>' : ""}
      <div class="form-grid">${sec.fields.map((f) => renderField(f, p)).join("")}</div>`;
  }

  async function openPerson(slug) {
    currentPerson = slug;
    showDetail();
    try {
      personCache = await A.api("GET", `/api/people/${encodeURIComponent(slug)}`);
      await loadPersonPhotos(slug);
    } catch (e) {
      A.toast(e.message, true);
      showOverview();
      return;
    }
    renderPerson();
  }

  function renderPerson() {
    if (!currentPerson || !personCache) return;
    const p = personCache, c = p.computed || {};
    const tabs = [
      ...peopleSchema.sections.map((s) => [s.id, `${s.icon} ${s.title}`]),
      ["gallery", "📸 Galleria Foto"],
      ["voice", "🎙 Voce e Impronta"],
      ["habits", "📈 Abitudini"],
    ];
    $("person-detail").innerHTML = `
      <div class="row" style="gap:16px; margin-bottom:16px; align-items:center;">
        ${avatar(p, 72)}
        <div style="flex:1">
          <h2 style="margin:0; font-weight:500;">${fmt.esc(c.display_name || p.name)}${p.nickname ? ` <span class="faint" style="font-size:15px">«${fmt.esc(p.nickname)}»</span>` : ""}</h2>
          <div class="faint" style="font-size:13px; margin-top:3px;">
            ${fmt.esc(peopleData.roles[p.role] || "")}${c.age != null ? ` · ${c.age} anni` : ""}${c.name_day ? ` · onomastico ${c.name_day.replace("-", "/")}` : ""}${p.occupation ? ` · ${fmt.esc(p.occupation)}` : ""}
            · Qualità Biometrica: <b style="color:var(--cyan);">${p.quality_pct || 75}%</b>
          </div>
        </div>
        <button class="btn sm danger" id="forget" title="Elimina persona e tutti i suoi dati">Elimina</button>
      </div>
      <div class="subtabs">${tabs.map(([id, t]) => `<button class="${id === currentSection ? "on" : ""}" data-sec="${id}">${t}</button>`).join("")}</div>
      <div id="section-body">${sectionHtml(p)}</div>
    `;
  }

  function autosave(key, value, delay = 600) {
    clearTimeout(saveTimers[key]);
    saveTimers[key] = setTimeout(async () => {
      try {
        await A.api("PUT", `/api/people/${encodeURIComponent(currentPerson)}`, { [key]: value });
        personCache[key] = value;
        A.flash("saved");
        if (["first_name", "last_name", "role", "birthday", "nickname"].includes(key)) loadPeople();
      } catch (e) {
        A.toast(e.message, true);
      }
    }, delay);
  }

  function readInput(el) {
    if (el.dataset.type === "bool") return el.checked;
    if (el.dataset.type === "tags") return el.value.split(",").map((x) => x.trim()).filter(Boolean);
    if (el.dataset.type === "number") return el.value === "" ? "" : Number(el.value);
    return el.value;
  }

  function collectList(key) {
    return [...document.querySelectorAll(`[data-list="${key}"] .list-row`)].map((row) => {
      const obj = {};
      row.querySelectorAll("[data-path]").forEach((el) => { obj[el.dataset.path.split(".")[2]] = readInput(el); });
      return obj;
    });
  }

  function onFieldChange(el) {
    const path = el.dataset.path; if (!path) return;
    const parts = path.split(".");
    if (parts.length === 3) autosave(parts[0], collectList(parts[0]));
    else autosave(path, readInput(el), el.dataset.type === "bool" || el.tagName === "SELECT" ? 0 : 600);
  }

  async function onDetailClick(e) {
    const t = e.target;
    if (t.dataset.sec) { currentSection = t.dataset.sec; renderPerson(); return; }
    if (t.dataset.add) {
      const key = t.dataset.add, f = peopleSchema.sections.flatMap((s) => s.fields).find((x) => x.key === key);
      personCache[key] = [...collectList(key), {}];
      t.closest(".list-field").outerHTML = renderField(f, personCache);
      return;
    }
    if (t.dataset.del) { const key = t.dataset.del; t.closest(".list-row").remove(); autosave(key, collectList(key), 0); return; }

    // Riprogetta riconoscimento
    if (t.id === "btn-reproject") {
      t.disabled = true;
      t.textContent = "Riprogettazione in corso…";
      try {
        const res = await A.api("POST", `/api/people/${encodeURIComponent(currentPerson)}/reproject`);
        A.toast(`Riconoscimento riprogettato con successo! Nuova qualità: ${res.quality_pct || 80}%`);
        await loadPeople();
        openPerson(currentPerson);
      } catch (err) {
        A.toast(err.message, true);
      } finally {
        t.disabled = false;
        t.textContent = "🔄 Riprogetta Riconoscimento";
      }
      return;
    }

    // Elimina singola foto dalla galleria
    if (t.classList.contains("btn-delete-photo")) {
      const photoId = t.dataset.photoId;
      if (!photoId) return;
      if (!confirm("Rimuovere questa foto dal modello di riconoscimento?")) return;
      try {
        await A.api("DELETE", `/api/people/${encodeURIComponent(currentPerson)}/photos/${encodeURIComponent(photoId)}`);
        A.toast("Foto rimossa con successo");
        await loadPeople();
        openPerson(currentPerson);
      } catch (err) {
        A.toast(err.message, true);
      }
      return;
    }

    if (t.id === "enroll-cam") {
      t.disabled = true; t.textContent = "Guarda la webcam… 4 secondi";
      try {
        const r = await A.api("POST", "/api/vision/people", { name: personCache.name });
        A.toast(`Nuovo campione acquisito (${r.samples} totali)`);
        await loadPeople();
        openPerson(currentPerson);
      } catch (err) {
        A.toast(err.message, true);
      } finally {
        t.disabled = false;
        t.textContent = "📷 Nuova Foto da Webcam";
      }
      return;
    }

    if (t.id === "forget") {
      if (!confirm("Eliminare definitivamente questa persona con volto, foto, dati e abitudini?")) return;
      try {
        await A.api("DELETE", `/api/people/${encodeURIComponent(currentPerson)}`);
        currentPerson = null;
        A.toast("Persona eliminata");
        showOverview();
        loadPeople();
      } catch (err) {
        A.toast(err.message, true);
      }
      return;
    }

    if (t.id === "forget-voice") {
      if (!confirm("Cancellare l'impronta vocale di questa persona?")) return;
      try {
        await A.api("DELETE", `/api/people/${encodeURIComponent(currentPerson)}/voiceprint`);
        A.toast("Impronta vocale cancellata");
        openPerson(currentPerson);
      } catch (err) {
        A.toast(err.message, true);
      }
      return;
    }
  }

  function init() {
    // Navigazione e ricerca
    $("btn-back-to-people")?.addEventListener("click", showOverview);

    $("people-search")?.addEventListener("input", (e) => {
      peopleFilter = e.target.value;
      renderTwoSections();
    });

    $("person-new")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = $("person-new-name").value.trim();
      if (!name) return;
      try {
        const p = await A.api("POST", "/api/people", { name });
        $("person-new-name").value = "";
        A.toast(`Persona creata: ${p.name}`);
        await loadPeople();
        openPerson(p.slug);
      } catch (err) {
        A.toast(err.message, true);
      }
    });

    // Ottimizzazione notturna manuale
    $("btn-nightly-optimize")?.addEventListener("click", async () => {
      const btn = $("btn-nightly-optimize");
      btn.disabled = true;
      btn.textContent = "🌙 Ottimizzazione in corso…";
      try {
        const res = await A.api("POST", "/api/people/optimize-nightly");
        A.toast(`Ottimizzazione biometrica completata per ${res.total_people || 0} persone!`);
        await loadPeople();
      } catch (err) {
        A.toast(err.message, true);
      } finally {
        btn.disabled = false;
        btn.textContent = "🌙 Ottimizza Riconoscimento";
      }
    });

    // Click su card registrata per aprire scheda
    $("registered-grid")?.addEventListener("click", (e) => {
      const openBtn = e.target.closest("[data-open]");
      if (openBtn) {
        openPerson(openBtn.dataset.open);
        return;
      }
      const card = e.target.closest(".person-card");
      if (card && card.dataset.slug) {
        openPerson(card.dataset.slug);
      }
    });

    $("scanned-grid")?.addEventListener("click", async (e) => {
      const card = e.target.closest(".person-card");
      if (card && card.dataset.scannedSlug && !e.target.closest("button") && !e.target.closest("input") && !e.target.closest("select")) {
        openPerson(card.dataset.scannedSlug);
        return;
      }

      const assignBtn = e.target.closest(".btn-assign-name");
      if (assignBtn) {
        const slug = assignBtn.dataset.slug;
        const input = document.querySelector(`[data-input-slug="${slug}"]`);
        const newName = input ? input.value.trim() : "";
        if (!newName) {
          A.toast("Inserisci un nome per la persona", true);
          return;
        }
        try {
          await A.api("PUT", `/api/people/${encodeURIComponent(slug)}`, { name: newName, is_scanned: false });
          A.toast(`Nome assegnato con successo: ${newName}!`);
          await loadPeople();
        } catch (err) {
          A.toast(err.message, true);
        }
        return;
      }

      const assocBtn = e.target.closest(".btn-do-assoc");
      if (assocBtn) {
        const fromSlug = assocBtn.dataset.slug;
        const select = document.querySelector(`[data-select-slug="${fromSlug}"]`);
        const toSlug = select ? select.value : "";
        if (!toSlug) {
          A.toast("Seleziona una persona registrata a cui associare il volto", true);
          return;
        }
        if (!confirm("Sei sicuro di voler associare questo volto alla persona selezionata? Le foto e i campioni biometrici verranno uniti.")) {
          return;
        }
        try {
          await A.api("POST", `/api/people/${encodeURIComponent(fromSlug)}/associate`, { to_slug: toSlug });
          A.toast("Volto e campioni associati con successo!");
          await loadPeople();
        } catch (err) {
          A.toast(err.message, true);
        }
        return;
      }
    });

    // Eventi scheda dettaglio
    const detailEl = $("person-detail");
    if (detailEl) {
      detailEl.addEventListener("input", (e) => {
        if (e.target.dataset.voice) {
          const t = e.target;
          autosave("voice", { ...(personCache.voice || {}), [t.dataset.voice]: t.type === "range" ? parseFloat(t.value) : t.value });
        } else if (e.target.dataset.path && e.target.type !== "checkbox" && e.target.tagName !== "SELECT") {
          onFieldChange(e.target);
        }
      });
      detailEl.addEventListener("change", (e) => {
        if (e.target.type === "checkbox" || e.target.tagName === "SELECT") {
          onFieldChange(e.target);
        }
      });
      detailEl.addEventListener("click", onDetailClick);
    }
  }

  function onState(s) {
    if (!A.isOn("people")) return;
    const pr = s.presence || {};
    const sig = JSON.stringify((pr.people || []).map((x) => x.slug));
    if (sig !== window.__presenceSig) {
      window.__presenceSig = sig;
      if (!currentPerson) renderTwoSections();
    }
  }

  A.tab("people", {
    title: "Persone", init, onState,
    load() { loadPeople(); },
    leave() {},
  });
})();
