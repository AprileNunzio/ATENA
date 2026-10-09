(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const SECTIONS = [["triggers", "Quando", "Aggiungi un innesco"], ["conditions", "Solo se", "Aggiungi una condizione"], ["actions", "Allora", "Aggiungi un'azione"]];
  const DAYS = [["mon", "Lun"], ["tue", "Mar"], ["wed", "Mer"], ["thu", "Gio"], ["fri", "Ven"], ["sat", "Sab"], ["sun", "Dom"]];
  const STATES = ["on", "off", "open", "closed", "home", "not_home", "playing", "locked", "unlocked"];
  const SVC = { turn_on: "Accendi", turn_off: "Spegni", toggle: "Inverti", open_cover: "Apri", close_cover: "Chiudi", stop_cover: "Ferma", lock: "Chiudi a chiave", unlock: "Apri serratura", media_play: "Riproduci", media_pause: "Pausa", start: "Avvia", return_to_base: "Torna alla base" };
  const MODES = { single: "Una alla volta (ignora se già in corso)", restart: "Riparti da capo", queued: "Metti in coda", parallel: "In parallelo" };
  let draft = null, onDone = null, showJson = false;

  const ents = () => (A.homeData ? A.homeData.entities : []);
  const area = (id) => ((A.homeData ? A.homeData.areas : []).find((a) => a.area_id === id) || {}).name || "";

  function entityOptions(value, controlOnly) {
    const list = ents().filter((e) => !e.hidden && !e.category && (!controlOnly || e.controllable)).sort((a, b) => (area(a.area_id) + a.name).localeCompare(area(b.area_id) + b.name));
    const known = list.some((e) => e.entity_id === value);
    return (value && !known ? `<option value="${fmt.esc(value)}" selected>${fmt.esc(value)} (sconosciuto)</option>` : '<option value="">Scegli…</option>')
      + list.map((e) => `<option value="${fmt.esc(e.entity_id)}" ${e.entity_id === value ? "selected" : ""}>${fmt.esc(area(e.area_id) ? `${area(e.area_id)} · ` : "")}${fmt.esc(e.name)}</option>`).join("");
  }

  function field([key, label, kind], v) {
    const val = v[key] ?? "";
    let input;
    if (kind === "entity") input = `<select data-f="${key}">${entityOptions(val, false)}</select>`;
    else if (kind === "controls") {
      const list = [].concat(val || []).length ? [].concat(val) : [""];
      input = `<div class="ha-au-multi" data-f="${key}" data-kind="multi">${list.map((x) => `<select>${entityOptions(x, true)}</select>`).join("")}<button type="button" class="btn sm" data-more>+ altro</button></div>`;
    } else if (kind === "service") {
      const domain = ([].concat(v.entity || [])[0] || "").split(".")[0], svcs = ((A.homeData || {}).services || {})[domain] || Object.keys(SVC);
      input = `<select data-f="${key}">${svcs.map((s) => `<option value="${s}" ${s === (val || "turn_on") ? "selected" : ""}>${fmt.esc(SVC[s] || s)}</option>`).join("")}</select>`;
    } else if (kind === "state") input = `<input data-f="${key}" list="ha-au-states" value="${fmt.esc(val)}">`;
    else if (kind === "sun") input = `<select data-f="${key}"><option value="sunrise" ${val === "sunrise" ? "selected" : ""}>Alba</option><option value="sunset" ${val !== "sunrise" ? "selected" : ""}>Tramonto</option></select>`;
    else if (kind === "daypart") input = `<select data-f="${key}"><option value="night">Di notte</option><option value="day" ${val === "day" ? "selected" : ""}>Di giorno</option></select>`;
    else if (kind === "days") input = `<div class="ha-au-days" data-f="${key}" data-kind="days">${DAYS.map(([d, l]) => `<label><input type="checkbox" value="${d}" ${(val || []).includes(d) ? "checked" : ""}>${l}</label>`).join("")}</div>`;
    else input = `<input data-f="${key}" type="${kind === "number" ? "number" : kind === "time" ? "time" : "text"}" value="${fmt.esc(val)}" ${kind === "number" ? 'step="any"' : ""}>`;
    return `<label class="ha-au-field">${fmt.esc(label)}${input}</label>`;
  }

  function blockHtml(section, item, i) {
    const table = A.homeBlocks.KINDS[section];
    const head = `<div class="ha-au-bhead"><select data-type>${Object.entries(table).map(([k, s]) => `<option value="${k}" ${k === item.type ? "selected" : ""}>${fmt.esc(s.label)}</option>`).join("")}${item.type === "raw" ? '<option value="raw" selected>Blocco avanzato</option>' : ""}</select>
      <button type="button" class="btn sm" data-del="${i}" title="Togli">✕</button></div>`;
    if (item.type === "raw") {
      return `<div class="ha-au-block raw" data-sec="${section}" data-i="${i}">${head}
        <div class="muted-note x-simple">Blocco avanzato creato in Home Assistant: resta com'è. Passa a «Esperto» per modificarlo.</div>
        <textarea class="mono x-expert" data-raw rows="5">${fmt.esc(JSON.stringify(item.raw, null, 2))}</textarea></div>`;
    }
    return `<div class="ha-au-block" data-sec="${section}" data-i="${i}">${head}<div class="ha-au-fields">${table[item.type].fields.map((f) => field(f, item.v)).join("")}</div></div>`;
  }

  function collect() {
    const box = $("ha-au-editor");
    draft.alias = box.querySelector("[data-alias]").value.trim();
    draft.description = box.querySelector("[data-desc]").value.trim();
    draft.mode = box.querySelector("[data-mode]").value;
    for (const [section] of SECTIONS) {
      draft[section] = [...box.querySelectorAll(`.ha-au-block[data-sec="${section}"]`)].map((el) => {
        if (el.querySelector("[data-raw]")) {
          try { return { type: "raw", raw: JSON.parse(el.querySelector("[data-raw]").value) }; } catch { throw new Error("Un blocco avanzato non è JSON valido"); }
        }
        const v = {};
        el.querySelectorAll("[data-f]").forEach((f) => {
          v[f.dataset.f] = f.dataset.kind === "days" ? [...f.querySelectorAll("input:checked")].map((c) => c.value)
            : f.dataset.kind === "multi" ? [...f.querySelectorAll("select")].map((x) => x.value).filter(Boolean) : f.value;
        });
        return { type: el.querySelector("[data-type]").value, v };
      });
    }
  }

  function config() {
    return { alias: draft.alias, description: draft.description, mode: draft.mode,
      ...Object.fromEntries(SECTIONS.map(([s]) => [s, draft[s].map((item) => A.homeBlocks.build(s, item))])) };
  }

  function render() {
    const box = $("ha-au-editor");
    box.innerHTML = `<div class="panel ha-au-edit">
      <div class="row" style="justify-content:space-between; flex-wrap:wrap; gap:8px">
        <div class="panel-title" style="margin:0">${draft.id ? "Modifica automazione" : "Nuova automazione"}</div>
        <div class="row x-expert" style="gap:6px"><button type="button" class="btn sm" data-json>${showJson ? "Editor visuale" : "{ } JSON"}</button></div></div>
      <div class="form-grid ha-au-meta"><div><label>Nome</label><input data-alias value="${fmt.esc(draft.alias)}" placeholder="es. Luce ingresso di notte"></div>
        <div><label>Descrizione</label><input data-desc value="${fmt.esc(draft.description)}"></div>
        <div class="x-expert"><label>Se parte mentre è già in corso</label><select data-mode>${Object.entries(MODES).map(([k, l]) => `<option value="${k}" ${k === draft.mode ? "selected" : ""}>${fmt.esc(l)}</option>`).join("")}</select></div></div>
      ${draft.warning ? `<div class="ha-au-warn">${fmt.esc(draft.warning)}</div>` : ""}
      ${showJson ? `<textarea class="mono" data-fulljson rows="18">${fmt.esc(JSON.stringify(config(), null, 2))}</textarea>`
        : SECTIONS.map(([s, title, add]) => `<div class="ha-au-sec"><div class="ha-au-sec-title">${title}</div>
          ${draft[s].map((item, i) => blockHtml(s, item, i)).join("") || `<div class="muted-note">${s === "conditions" ? "Nessuna condizione: parte sempre." : "Ancora vuoto."}</div>`}
          <button type="button" class="btn sm" data-add="${s}">+ ${add}</button></div>`).join("")}
      <datalist id="ha-au-states">${STATES.map((x) => `<option value="${x}">`).join("")}</datalist>
      <div class="actions"><button type="button" class="btn primary" data-save>Salva in Home Assistant</button><button type="button" class="btn" data-cancel>Annulla</button></div></div>`;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function open(entry, done) {
    onDone = done; showJson = false;
    const cfg = entry.config || {};
    draft = { id: entry.id || null, alias: cfg.alias || "", description: cfg.description || "", mode: cfg.mode || "single", warning: entry.warning || "" };
    for (const [s] of SECTIONS) {
      const raw = cfg[s] ?? cfg[s.slice(0, -1)] ?? [];
      draft[s] = entry.blank ? (s === "conditions" ? [] : [{ type: Object.keys(A.homeBlocks.KINDS[s])[0], v: {} }])
        : [].concat(raw).map((b) => A.homeBlocks.parse(s, b));
    }
    render();
  }

  async function save() {
    let body;
    try {
      if (showJson) body = JSON.parse($("ha-au-editor").querySelector("[data-fulljson]").value);
      else { collect(); body = config(); }
    } catch (e) { A.toast(e.message || "JSON non valido", true); return; }
    try {
      const r = draft.id ? await A.api("PUT", `/api/home/automations/id/${encodeURIComponent(draft.id)}`, { config: body })
        : await A.api("POST", "/api/home/automations", { config: body });
      A.toast(r.unknown_entities.length ? `Salvata, ma questi dispositivi non esistono: ${r.unknown_entities.join(", ")}` : "Automazione salvata in Home Assistant", !!r.unknown_entities.length);
      close(); if (onDone) onDone();
    } catch (e) { A.toast(e.message, true); }
  }

  function close() { $("ha-au-editor").innerHTML = ""; draft = null; }

  function init() {
    const box = $("ha-au-editor");
    box.addEventListener("click", (e) => {
      const t = e.target;
      if (t.closest("[data-save]")) return save();
      if (t.closest("[data-cancel]")) return close();
      if (t.closest("[data-json]")) {
        try {
          if (showJson) open({ id: draft.id, config: JSON.parse(box.querySelector("[data-fulljson]").value) }, onDone);
          else { collect(); showJson = true; render(); }
        } catch (err) { A.toast(err.message || "JSON non valido", true); }
        return;
      }
      const add = t.closest("[data-add]");
      if (add) { collect(); const s = add.dataset.add; draft[s].push({ type: Object.keys(A.homeBlocks.KINDS[s])[0], v: {} }); return render(); }
      const more = t.closest("[data-more]");
      if (more) { collect(); const blk = more.closest(".ha-au-block"); draft[blk.dataset.sec][Number(blk.dataset.i)].v.entity.push(""); return render(); }
      const del = t.closest("[data-del]");
      if (del) { collect(); const blk = del.closest(".ha-au-block"); draft[blk.dataset.sec].splice(Number(blk.dataset.i), 1); return render(); }
    });
    box.addEventListener("change", (e) => {
      const t = e.target, blk = t.closest(".ha-au-block");
      if (!blk || !draft) return;
      if (t.matches("[data-type]")) { collect(); draft[blk.dataset.sec][Number(blk.dataset.i)] = { type: t.value, v: {} }; return render(); }
      if (t.closest('[data-f="entity"]') && blk.dataset.sec === "actions") { collect(); render(); }
    });
  }

  A.homeAutoEdit = { init, open, close };
})();
