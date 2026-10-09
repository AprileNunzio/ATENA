(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  let rows = [], query = "";

  const when = (ts) => (ts ? new Date(ts).toLocaleString(undefined, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "mai");
  const line = (label, items, cls) => (items && items.length ? `<div class="ha-au-line ${cls}"><b>${label}</b><span>${items.map(fmt.esc).join(" · ")}</span></div>` : "");

  function card(r) {
    const s = r.summary;
    return `<div class="ha-au-card ${r.state === "on" ? "on" : ""}" data-eid="${fmt.esc(r.entity_id)}" data-id="${fmt.esc(r.id)}">
      <div class="ha-au-top">
        <label class="ha-switch" title="${r.state === "on" ? "Attiva: tocca per spegnerla" : "Spenta: tocca per attivarla"}"><input type="checkbox" data-toggle ${r.state === "on" ? "checked" : ""}><span></span></label>
        <div style="min-width:0; flex:1"><div class="ha-au-name">${fmt.esc(r.alias)}</div>
          ${r.description ? `<div class="muted-note">${fmt.esc(r.description)}</div>` : ""}</div></div>
      ${s ? line("Quando", s.when, "w") + line("Solo se", s.only_if, "c") + line("Allora", s.then, "t") : `<div class="ha-au-warn">${fmt.esc(r.error || "Configurazione non leggibile")}</div>`}
      <div class="ha-au-foot"><span class="faint">Ultima volta: ${when(r.last_triggered)}</span>
        <span class="x-expert faint mono">${fmt.esc(r.entity_id)} · ${fmt.esc(r.mode)}</span></div>
      <div class="actions">
        <button type="button" class="btn sm" data-run>▶ Esegui ora</button>
        ${r.id ? '<button type="button" class="btn sm primary" data-edit>Modifica</button><button type="button" class="btn sm x-expert" data-traces>Tracce</button><button type="button" class="btn sm danger" data-delete>Elimina</button>' : '<span class="faint" style="font-size:11px">Definita in YAML: modificabile solo in Home Assistant</span>'}
      </div>
      <div class="ha-au-traces" data-tr></div></div>`;
  }

  function render() {
    const q = query.toLowerCase();
    const list = rows.filter((r) => !q || JSON.stringify([r.alias, r.description, r.summary]).toLowerCase().includes(q));
    $("ha-au-list").innerHTML = list.map(card).join("") || `<div class="panel faint">${rows.length ? "Nessuna automazione corrisponde alla ricerca." : "Nessuna automazione ancora: creane una a parole o con «+ Nuova»."}</div>`;
  }

  async function load() {
    try { rows = (await A.api("GET", "/api/home/automations")).automations; } catch (e) { $("ha-au-list").innerHTML = `<div class="panel faint">${fmt.esc(e.message)}</div>`; return; }
    render();
  }

  async function traces(el, id) {
    const box = el.querySelector("[data-tr]");
    box.textContent = "Carico…";
    try {
      const t = (await A.api("GET", `/api/home/automations/id/${encodeURIComponent(id)}/traces`)).traces;
      box.innerHTML = t.map((x) => `<div><span class="mono faint">${when(x.start)}</span> ${x.error ? `<span style="color:var(--red)">✕ ${fmt.esc(x.error)}</span>` : `✓ ${fmt.esc(x.result || x.state || "")}`}${x.trigger ? ` <span class="faint">· ${fmt.esc(x.trigger)}</span>` : ""}</div>`).join("") || '<div class="faint">Nessuna esecuzione registrata.</div>';
    } catch (e) { box.textContent = e.message; }
  }

  async function act(e) {
    const el = e.target.closest(".ha-au-card");
    if (!el) return;
    const eid = el.dataset.eid, id = el.dataset.id;
    try {
      if (e.target.closest("[data-run]")) { await A.api("POST", `/api/home/automations/${encodeURIComponent(eid)}/run`); A.toast("Automazione avviata"); setTimeout(load, 1200); }
      else if (e.target.closest("[data-edit]")) { const full = await A.api("GET", `/api/home/automations/${encodeURIComponent(eid)}`); A.homeAutoEdit.open({ id, config: full.config }, load); }
      else if (e.target.closest("[data-traces]")) traces(el, id);
      else if (e.target.closest("[data-delete]")) {
        if (!confirm("Eliminare questa automazione da Home Assistant? Non si può annullare.")) return;
        await A.api("DELETE", `/api/home/automations/id/${encodeURIComponent(id)}`); A.toast("Automazione eliminata"); load();
      }
    } catch (err) { A.toast(err.message, true); }
  }

  async function toggle(e) {
    const box = e.target.closest("[data-toggle]");
    if (!box) return;
    const el = box.closest(".ha-au-card");
    try { await A.api("POST", `/api/home/automations/${encodeURIComponent(el.dataset.eid)}/toggle`, { on: box.checked }); A.toast(box.checked ? "Automazione attivata" : "Automazione spenta"); setTimeout(load, 800); }
    catch (err) { box.checked = !box.checked; A.toast(err.message, true); }
  }

  async function design(e) {
    e.preventDefault();
    const text = $("ha-au-ai-text").value.trim();
    if (!text) return;
    const btn = $("ha-au-ai").querySelector("button");
    btn.disabled = true; btn.textContent = "Progetto…";
    try {
      const r = await A.api("POST", "/api/home/automations-draft", { text });
      const warning = r.unknown_entities.length ? `Attenzione: il cervello ha usato dispositivi che non trovo (${r.unknown_entities.join(", ")}). Controlla prima di salvare.` : "Bozza preparata dal cervello: controlla e salva.";
      A.homeAutoEdit.open({ config: r.config, warning }, load);
    } catch (err) { A.toast(err.message, true); }
    finally { btn.disabled = false; btn.textContent = "Progettala"; }
  }

  function init() {
    A.homeAutoEdit.init();
    $("ha-au-list").addEventListener("click", act);
    $("ha-au-list").addEventListener("change", toggle);
    $("ha-au-new").addEventListener("click", () => A.homeAutoEdit.open({ blank: true }, load));
    $("ha-au-q").addEventListener("input", (e) => { query = e.target.value; render(); });
    $("ha-au-ai").addEventListener("submit", design);
  }

  A.homeAutos = { init, load };
})();
