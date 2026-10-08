(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  let brainData = null;
  let catQuery = "";
  let catCategory = "all";
  let catSort = "web_rank";
  let catPage = 1;
  const PAGE_SIZE = 8;

  const ICON = { cloud: "☁", server: "🖧", local: "🖥" };
  const originBadge = (e) => e.origin === "local" ? '<span class="badge br-local">🖥 locale</span>'
    : `<span class="badge br-${e.origin}">${ICON[e.origin]} ${fmt.esc(e.provider)}</span>`;
  const seconds = (ms) => `${(ms / 1000).toFixed(1).replace(".", ",")} s`;

  function showSubpage(subId) {
    const subnav = $("br-subnav");
    if (subnav) {
      subnav.querySelectorAll("[data-sub]").forEach((b) => b.classList.toggle("on", b.dataset.sub === subId));
    }
    ["dashboard", "assign", "add"].forEach((s) => {
      const el = $(`br-sub-${s}`);
      if (el) el.classList.toggle("on", s === subId);
    });
    try { localStorage.setItem("atena_brain_subpage", subId); } catch (_) {}
    if (subId === "assign" && A.brainAssign) A.brainAssign.load();
    if (subId === "add") { loadModels(); loadOllama(); }
  }

  async function loadModels() {
    try {
      const d = await A.api("GET", "/api/models");
      $("models-body").innerHTML = d.models.map((m) => `<tr><td class="mono" style="font-weight:600">${fmt.esc(m.name)}</td><td class="mono">${fmt.bytes(m.size)}</td>
        <td>${d.loaded.includes(m.name) ? '<span class="badge ok">in memoria</span>' : '<span class="badge">su disco</span>'}</td>
        <td style="text-align:right"><button class="btn sm danger" data-del="${fmt.esc(m.name)}">Elimina</button></td></tr>`).join("")
        || `<tr><td colspan="4" class="faint">Nessun modello locale scaricato: Atena può usare i server remoti o il cloud.</td></tr>`;
    } catch (e) { $("models-body").innerHTML = `<tr><td colspan="4" class="faint">${fmt.esc(e.message)}</td></tr>`; }
  }

  async function loadBrains() {
    try {
      brainData = await A.api("GET", "/api/brains");
    } catch (e) {
      $("br-catalog").innerHTML = `<div class="faint">${fmt.esc(e.message)}</div>`;
      return;
    }
    renderBrains();
  }

  function nowCard(role) {
    const title = `${role.icon} ${role.label}`;
    if (!role.active) {
      return `<div class="br-now-kind">${title}</div><div class="br-now-model warn">Nessun cervello disponibile</div>
        <div class="faint" style="font-size:12px">Scarica un modello locale o collega un servizio cloud per attivare questo ruolo.</div>`;
    }
    const st = (role.entries.find((e) => e.name === role.active.ref) || {}).stats;
    const fallbacks = role.entries.filter((e) => e.name !== role.active.ref).slice(0, 2);
    const fbText = fallbacks.length ? `<div class="faint" style="font-size:11px; margin-top:4px">Ripieghi: ${fallbacks.map((f) => fmt.esc(f.model)).join(" → ")}</div>` : "";
    return `<div class="br-now-kind">${title}</div><div class="br-now-model">${fmt.esc(role.active.model)}</div>
      <div class="br-now-meta">${originBadge(role.active)}${st ? ` <span class="faint">${st.ok} risposte · ~${seconds(st.avg_ms)}</span>` : ""}</div>
      ${fbText}`;
  }

  function autoNote(d, role) {
    if (role.id === "chat") return `Automatico: scelto da Atena in base all'hardware (veloce: ${fmt.esc(d.fast)}).`;
    if (role.id === "deep") return `Automatico: scelto da Atena in base all'hardware (potente: ${fmt.esc(d.main)}).`;
    return "Nessun modello dedicato: questo agente usa gli stessi modelli del Ragionamento. Scegline uno qui sotto, oppure apri «Agenti e componenti» per personalizzare ogni singolo agente con parametri e istruzioni.";
  }

  function priorityList(d, role, cat) {
    const activeRef = role.active && role.active.ref;
    const items = role.entries.map((m, i) => {
      const c = cat[m.name] || {}, st = m.stats;
      const status = m.origin === "server"
        ? (m.available ? '<span style="color:var(--green)">collegato</span>' : '<span style="color:var(--amber)">server rimosso</span>')
        : m.origin === "cloud"
        ? (m.available ? '<span style="color:var(--green)">collegato</span>' : '<span style="color:var(--amber)">chiave mancante</span>')
        : (m.available ? '<span style="color:var(--green)">scaricato</span>' : '<span style="color:var(--amber)">da scaricare</span>');
      const sub = [m.name === activeRef ? '<b style="color:var(--cyan)">• in uso</b>' : "", `${ICON[m.origin]} ${fmt.esc(m.provider)}`, status,
        c.fit && c.fit.label, st ? `${st.ok} risposte · ~${seconds(st.avg_ms)}${st.fail ? ` · ${st.fail} err` : ""}` : ""].filter(Boolean).join(" · ");
      return A.prioItem(m.name, i, c.label && c.label !== m.name ? `${c.label} · ${m.model}` : m.model, sub, !m.available, false);
    }).join("");
    return items + (role.custom ? "" : `<div class="muted-note" style="margin:4px 6px">${autoNote(d, role)}</div>`);
  }

  function rolePanel(role) {
    return `<div class="panel" data-role="${role.id}">
      <div class="panel-title">${role.icon} ${fmt.esc(role.label)}</div>
      <div class="muted-note">${fmt.esc(role.hint)}</div>
      <div class="prio" data-prio="${role.id}"></div>
      <div class="br-pick" style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px">
        <select data-br-pick="${role.id}" style="flex:1; min-width:180px" aria-label="Modello per ${fmt.esc(role.label)}"></select>
        <button class="btn sm primary" data-br-add="${role.id}">Usa questo modello</button></div>
      <div class="actions" style="margin-top:10px"><button class="btn sm" data-br-reset="${role.id}">Ripristina Automatico</button>
        <button class="btn sm" data-br-agents="1">Agenti e componenti →</button></div>
    </div>`;
  }

  function pickOptions(d, role, cat) {
    const mine = new Set(role.custom ? role.entries.map((e) => e.name) : []);
    const known = new Map();
    d.roles.flatMap((r) => r.entries).forEach((e) => known.set(e.name, `${ICON[e.origin] || ""} ${e.model}${e.available ? "" : " (non disponibile)"}`));
    d.catalog.filter((m) => m.installed).forEach((m) => { if (!known.has(m.name)) known.set(m.name, `${ICON.local} ${(cat[m.name] || m).label || m.name}`); });
    const items = [...known].filter(([name]) => !mine.has(name));
    return `<option value="">Scegli un modello per questo agente…</option>${items.map(([name, label]) => `<option value="${fmt.esc(name)}">${fmt.esc(label)}</option>`).join("")}`;
  }

  function mountRoles(host, roles) {
    host.innerHTML = roles.map(rolePanel).join("");
    host.querySelectorAll("[data-prio]").forEach((list) => A.makeSortable(list, (items) => saveBrains({ [list.dataset.prio]: items })));
  }

  function filterAndSortCatalog(catalog) {
    const q = catQuery.toLowerCase().trim();
    let list = catalog.filter((m) => {
      if (q) {
        const text = `${m.name} ${m.label} ${m.notes || ""} ${m.category || ""}`.toLowerCase();
        if (!text.includes(q)) return false;
      }
      if (catCategory === "reasoning") return m.category === "reasoning" || m.name.includes("r1");
      if (catCategory === "chat") return m.category === "chat" || (m.roles && m.roles.includes("chat"));
      if (catCategory === "code") return m.category === "code" || m.name.includes("coder");
      if (catCategory === "vision") return m.category === "vision" || m.name.includes("vision") || m.name.includes("llava");
      if (catCategory === "light") return m.size_gb != null && m.size_gb <= 3.0;
      if (catCategory === "heavy") return m.size_gb != null && m.size_gb >= 7.0;
      return true;
    });

    if (catSort === "web_rank") {
      list.sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
    } else if (catSort === "size_asc") {
      list.sort((a, b) => (a.size_gb ?? 999) - (b.size_gb ?? 999));
    } else if (catSort === "size_desc") {
      list.sort((a, b) => (b.size_gb ?? 0) - (a.size_gb ?? 0));
    } else if (catSort === "name_asc") {
      list.sort((a, b) => a.name.localeCompare(b.name));
    }
    return list;
  }

  function catalogCard(d, m) {
    const buttons = d.roles.slice(0, 2).map((r) => {
      const inRole = r.entries.some((e) => e.name === m.name);
      return `<button class="btn sm" data-add="${r.id}" data-m="${fmt.esc(m.name)}" ${inRole ? "disabled" : ""} title="Aggiungi a ${fmt.esc(r.label)}">+ ${r.icon} ${fmt.esc(r.label.split(" ")[0])}</button>`;
    }).join("");

    const rankBadge = m.rank && m.rank <= 10
      ? `<span class="badge" style="color:var(--amber); border-color:rgba(255,196,61,0.4)">⭐ Top #${m.rank} Web</span>`
      : (m.rank ? `<span class="badge" style="color:var(--cyan); border-color:rgba(41,224,255,0.3)">#${m.rank} Web</span>` : "");
    const recBadge = m.name === d.suggested.chat ? '<span class="badge ok">consigliato ⚡</span>'
      : (m.name === d.suggested.deep ? '<span class="badge ok">consigliato 🧠</span>' : "");
    const installedBadge = m.installed ? '<span class="badge ok">✓ Installato</span>' : '';
    const fitLevel = m.fit ? m.fit.level : "ok";
    const fitLabel = m.fit ? m.fit.label : "pronto";

    return `<div class="cat-card">
      <div>
        <div class="cat-card-top">
          <div>
            <div class="cat-card-title">${fmt.esc(m.label)}</div>
            <div class="cat-card-sub faint mono">${fmt.esc(m.name)}${m.size_gb ? ` · ${m.size_gb} GB` : ""}</div>
          </div>
          <div>${installedBadge}</div>
        </div>
        <div class="cat-card-badges">${rankBadge}${recBadge}</div>
        <div class="cat-card-notes" style="margin-top:8px">${fmt.esc(m.notes || "")}</div>
      </div>
      <div>
        <div class="cat-card-bottom">
          <div class="cat-card-fit ${fitLevel}">${fmt.esc(fitLabel)}</div>
          <div class="cat-card-actions">
            ${m.installed ? "" : `<button class="btn sm primary" data-dl="${fmt.esc(m.name)}" data-size="${m.size_gb || ""}">Scarica</button>`}
            ${buttons}
          </div>
        </div>
      </div>
    </div>`;
  }

  function renderCatalog() {
    if (!brainData) return;
    const d = brainData;
    const filtered = filterAndSortCatalog(d.catalog);
    const totalPages = Math.ceil(filtered.length / PAGE_SIZE) || 1;
    if (catPage > totalPages) catPage = totalPages;
    if (catPage < 1) catPage = 1;

    const startIdx = (catPage - 1) * PAGE_SIZE;
    const pageItems = filtered.slice(startIdx, startIdx + PAGE_SIZE);

    const catHost = $("br-catalog");
    if (pageItems.length === 0) {
      catHost.innerHTML = `<div class="panel" style="grid-column:1/-1; text-align:center; padding:30px">
        <div class="dim" style="font-size:15px">Nessun modello trovato con questi filtri.</div>
        <div class="faint" style="font-size:12px; margin-top:6px">Prova a cambiare il testo cercato o seleziona «Tutti i Modelli».</div>
      </div>`;
    } else {
      catHost.innerHTML = pageItems.map((m) => catalogCard(d, m)).join("");
    }

    const prevBtn = $("cat-prev"), nextBtn = $("cat-next"), infoSpan = $("cat-page-info"), numsHost = $("cat-page-numbers");
    if (prevBtn) prevBtn.disabled = catPage <= 1;
    if (nextBtn) nextBtn.disabled = catPage >= totalPages;
    if (infoSpan) infoSpan.textContent = `Pagina ${catPage} di ${totalPages} · ${filtered.length} modelli totali`;

    if (numsHost) {
      let numsHtml = "";
      for (let p = 1; p <= totalPages; p++) {
        if (p === 1 || p === totalPages || (p >= catPage - 1 && p <= catPage + 1)) {
          numsHtml += `<button type="button" class="cat-page-btn ${p === catPage ? "on" : ""}" data-page="${p}">${p}</button>`;
        } else if (p === catPage - 2 || p === catPage + 2) {
          numsHtml += `<span class="dim" style="padding:0 2px">…</span>`;
        }
      }
      numsHost.innerHTML = numsHtml;
    }
  }

  function renderBrains() {
    const d = brainData, cat = Object.fromEntries(d.catalog.map((m) => [m.name, m]));
    $("br-routing").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.r === d.routing));
    $("br-now-grid").innerHTML = d.roles.map((r) => `<div class="br-now-card">${nowCard(r)}</div>`).join("");
    const l = d.last_used || {};
    $("br-last").innerHTML = l.model ? `Ultima risposta elaborata: <b>${fmt.esc(l.model)}</b> ${originBadge(l)} in ${seconds(l.ms)}` : "";
    const host = $("br-roles");
    if (host.children.length !== d.roles.length) mountRoles(host, d.roles);
    d.roles.forEach((r) => {
      host.querySelector(`[data-prio="${r.id}"]`).innerHTML = priorityList(d, r, cat);
      host.querySelector(`[data-br-pick="${r.id}"]`).innerHTML = pickOptions(d, r, cat);
    });
    const hw = d.hardware || {};
    $("br-hw").textContent = `${hw.ram_gb || "?"} GB RAM · ${hw.gpu ? `${hw.gpu} ${hw.vram_gb} GB` : "solo CPU (nessuna GPU dedicata)"}`;
    renderCatalog();
  }

  async function saveBrains(body) {
    try {
      brainData = await A.api("PUT", "/api/brains", body);
      renderBrains();
    } catch (e) {
      A.toast(e.message, true);
      loadBrains();
    }
  }

  async function addTo(kind, name, first = false) {
    if (!brainData) await loadBrains();
    const role = brainData.roles.find((r) => r.id === kind);
    if (!role) return;
    const list = role.entries.map((x) => x.name);
    if (list.includes(name)) { A.toast("È già presente nella lista del ruolo"); return; }
    await saveBrains({ [kind]: first ? [name, ...list] : [...list, name] });
    A.toast(`Aggiunto a ${role.icon} ${role.label}: trascinalo per definirne la priorità`);
  }

  async function pullModel(name, size) {
    if (!confirm(`Scaricare ${name}${size ? ` (${size} GB)` : ""}? Il download continuerà in background.`)) return false;
    try {
      await A.api("POST", "/api/models/pull", { name });
      A.toast(`Download di ${name} avviato con successo`);
      return true;
    } catch (e) {
      A.toast(e.message, true);
      return false;
    }
  }

  function showSource(v) {
    $("br-source").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.v === v));
    ["local", "servers", "cloud"].forEach((x) => $(`br-view-${x}`).classList.toggle("on", x === v));
  }

  async function loadOllama() {
    try {
      const c = await A.api("GET", "/api/config");
      const item = (c.editable || []).find((x) => x.key === "ATENA_OLLAMA_URL");
      $("ol-url").value = (item && item.value) || "";
    } catch (e) {}
  }

  async function testOllama() {
    $("ol-res").textContent = "Verifica connessione in corso…";
    try {
      const r = await A.api("POST", "/api/brains/ollama/test", { url: $("ol-url").value.trim() });
      $("ol-res").innerHTML = r.ok ? `✓ ${fmt.esc(r.url)} risponde: Ollama ${fmt.esc(r.version)}, ${r.models.length} modelli installati${r.models.length ? ` (${r.models.slice(0, 6).map(fmt.esc).join(", ")}${r.models.length > 6 ? "…" : ""})` : ""}`
        : `✕ ${fmt.esc(r.url)}: ${fmt.esc(r.error)}`;
      return r.ok;
    } catch (e) { $("ol-res").textContent = `✕ ${e.message}`; return false; }
  }

  function roleLabel(id) {
    const role = brainData && brainData.roles.find((r) => r.id === id);
    return role ? `${role.icon} ${role.label}` : id;
  }

  function init() {
    $("br-subnav").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sub]");
      if (b) showSubpage(b.dataset.sub);
    });

    $("ol-test").addEventListener("click", testOllama);
    $("ol-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if ($("ol-url").value.trim() && !(await testOllama()) && !confirm("Il server non risponde: salvare comunque l'indirizzo?")) return;
      try {
        await A.api("PUT", "/api/config", { ATENA_OLLAMA_URL: $("ol-url").value.trim() });
        A.toast($("ol-url").value.trim() ? "Indirizzo Ollama salvato" : "Ripristinato Ollama locale predefinito");
        loadOllama(); loadModels(); loadBrains();
      } catch (err) { A.toast(err.message, true); }
    });

    $("models-body").addEventListener("click", async (e) => {
      const name = e.target.dataset.del;
      if (!name || !confirm(`Eliminare il modello locale ${name} per liberare spazio su disco?`)) return;
      try {
        await A.api("DELETE", `/api/models/${encodeURIComponent(name)}`);
        A.toast(`Modello ${name} eliminato`);
        loadModels();
        loadBrains();
      } catch (err) { A.toast(err.message, true); }
    });

    $("pull-btn").addEventListener("click", async () => {
      const name = $("pull-name").value.trim();
      if (!name) return;
      try {
        await A.api("POST", "/api/models/pull", { name });
        A.toast(`Download di ${name} avviato in background`);
      } catch (e) { A.toast(e.message, true); }
    });

    $("br-routing").addEventListener("click", (e) => {
      const b = e.target.closest("[data-r]");
      if (b) saveBrains({ routing: b.dataset.r }).then(() => A.toast("Modalità di instradamento aggiornata"));
    });

    $("br-roles").addEventListener("click", (e) => {
      const b = e.target.closest("[data-br-reset]");
      if (b) saveBrains({ [b.dataset.brReset]: [] }).then(() => A.toast("Lista del ruolo ripristinata in automatico"));
      const add = e.target.closest("[data-br-add]");
      if (add) {
        const id = add.dataset.brAdd, picked = $("br-roles").querySelector(`[data-br-pick="${id}"]`).value;
        const role = brainData.roles.find((r) => r.id === id);
        if (!picked || !role) { A.toast("Scegli prima un modello dall'elenco", true); return; }
        const current = role.custom ? role.entries.map((x) => x.name).filter((n) => n !== picked) : [];
        saveBrains({ [id]: [picked, ...current] }).then(() => A.toast(`${role.label}: ora usa ${picked} per primo`));
      }
      if (e.target.closest("[data-br-agents]")) showSubpage("assign");
    });

    $("br-source").addEventListener("click", (e) => {
      const b = e.target.closest("[data-v]");
      if (b) showSource(b.dataset.v);
    });

    $("cat-search").addEventListener("input", (e) => {
      catQuery = e.target.value;
      catPage = 1;
      renderCatalog();
    });

    $("cat-sort").addEventListener("change", (e) => {
      catSort = e.target.value;
      catPage = 1;
      renderCatalog();
    });

    $("cat-pills").addEventListener("click", (e) => {
      const b = e.target.closest("[data-cat]");
      if (!b) return;
      $("cat-pills").querySelectorAll(".cat-pill").forEach((p) => p.classList.toggle("on", p === b));
      catCategory = b.dataset.cat;
      catPage = 1;
      renderCatalog();
    });

    $("cat-prev").addEventListener("click", () => {
      if (catPage > 1) { catPage--; renderCatalog(); }
    });

    $("cat-next").addEventListener("click", () => {
      catPage++;
      renderCatalog();
    });

    $("cat-page-numbers").addEventListener("click", (e) => {
      const b = e.target.closest("[data-page]");
      if (b) { catPage = parseInt(b.dataset.page, 10); renderCatalog(); }
    });

    $("br-catalog").addEventListener("click", async (e) => {
      const add = e.target.closest("[data-add]"), dl = e.target.closest("[data-dl]");
      if (dl) return pullModel(dl.dataset.dl, dl.dataset.size);
      if (!add) return;
      const m = brainData.catalog.find((x) => x.name === add.dataset.m);
      await addTo(add.dataset.add, add.dataset.m);
      if (m && !m.installed) pullModel(m.name, m.size_gb);
    });

    $("br-test").addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = $("br-q").value.trim();
      if (!text) return;
      try {
        const r = await A.api("POST", "/api/brains/test", { text });
        $("br-res").innerHTML = `${roleLabel(r.kind)} <span class="faint">— ${fmt.esc(r.reason)} · risponderà <b>${fmt.esc(r.models[0] || "nessuno")}</b>${r.models.length > 1 ? `, ripieghi ordinati: ${r.models.slice(1).map(fmt.esc).join(" → ")}` : ""}</span>`;
      } catch (err) { A.toast(err.message, true); }
    });

    try {
      const savedSub = localStorage.getItem("atena_brain_subpage");
      if (savedSub && ["dashboard", "assign", "add"].includes(savedSub)) {
        showSubpage(savedSub);
      }
    } catch (_) {}
  }

  function onState(s) {
    const mp = s.model_pull;
    if (!mp) return;
    $("pull-status").textContent = `${mp.name}: ${mp.status}${mp.percent ? ` — ${mp.percent}%` : ""}`;
    $("pull-bar").style.width = `${mp.percent || 0}%`;
    const sig = `${mp.name}|${mp.status}`;
    if (sig !== window.__pullSig) {
      window.__pullSig = sig;
      if (A.isOn("models") && /completato|errore/.test(mp.status)) {
        loadModels();
        loadBrains();
      }
    }
  }

  A.brain = { reload: loadBrains, addTo, lists: () => brainData, showSource, showSubpage };
  A.tab("models", {
    title: "Cervello",
    init() {
      init();
      if (A.brainCloud) A.brainCloud.init();
      if (A.brainServers) A.brainServers.init();
      if (A.brainAssign) A.brainAssign.init();
    },
    async load() {
      loadModels();
      loadOllama();
      await loadBrains();
      if (A.brainCloud) A.brainCloud.load();
      if (A.brainServers) A.brainServers.load();
      if (A.brainAssign) A.brainAssign.load();
    },
    onState
  });
})();
