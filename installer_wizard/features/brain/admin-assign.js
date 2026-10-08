(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const esc = fmt.esc;
  const ICON = { cloud: "☁", server: "🖧", local: "🖥" };
  const KEEP = [["", "Predefinito"], ["5m", "5 minuti"], ["30m", "30 minuti"], ["1h", "1 ora"], ["6h", "6 ore"], ["24h", "24 ore"], ["-1", "Sempre"]];
  const ORIGIN_LABEL = { local: "Questo server", server: "Altri server", cloud: "Cloud" };
  let data = null, keep = { overrides: {} }, editing = null, draft = null;

  const label = (ref) => (data.pool.find((p) => p.ref === ref) || { label: ref }).label;
  const roleName = (id) => { const r = data.roles.find((x) => x.id === id); return r ? `${r.icon} ${r.label}` : id; };

  function chips(chain) {
    if (!chain.length) return '<span class="warn">nessun cervello disponibile</span>';
    return chain.map((c, i) => `<span class="as-chip ${c.available ? "" : "off"} ${i === 0 ? "first" : ""}" title="${esc(c.provider)}">${i === 0 ? "▶ " : `${i + 1}· `}${ICON[c.origin] || ""} ${esc(c.model)}</span>`).join("");
  }

  function ownList() {
    if (!draft.order.length) return '<div class="faint">Nessun cervello dedicato: usa la lista del ruolo.</div>';
    return draft.order.map((ref, i) => `<div class="as-own"><span class="mono">${esc(label(ref))}</span><span class="actions">
      <button class="btn sm" data-up="${i}" ${i ? "" : "disabled"}>↑</button><button class="btn sm" data-down="${i}" ${i < draft.order.length - 1 ? "" : "disabled"}>↓</button>
      <button class="btn sm danger" data-rm="${i}">✕</button></span></div>`).join("");
  }

  function pickOptions() {
    return ["local", "server", "cloud"].map((origin) => {
      const items = data.pool.filter((p) => p.origin === origin && !draft.order.includes(p.ref));
      if (!items.length) return "";
      return `<optgroup label="${ORIGIN_LABEL[origin]}">${items.map((p) => `<option value="${esc(p.ref)}">${esc(p.label)}${p.available ? "" : " (non disponibile)"}</option>`).join("")}</optgroup>`;
    }).join("");
  }

  const blank = (v) => (v === null || v === undefined ? "" : v);

  function tuningFields() {
    const t = draft.tuning;
    return `<div class="as-sub">Parametri dell'agente (vuoto = predefinito)</div>
      <div class="form-grid">
        <label>Creatività (temperatura 0 – 1,5)<input data-t="temperature" type="number" min="0" max="1.5" step="0.1" value="${esc(blank(t.temperature))}" placeholder="predefinita"></label>
        <label>Lunghezza massima della risposta (token)<input data-t="max_tokens" type="number" min="64" max="16384" step="64" value="${esc(blank(t.max_tokens))}" placeholder="predefinita"></label>
        <label>Tempo massimo (secondi)<input data-t="timeout" type="number" min="5" max="600" step="5" value="${esc(blank(t.timeout))}" placeholder="predefinito"></label>
      </div>
      <label>Istruzioni personalizzate per questo agente<textarea data-t="instructions" rows="3" maxlength="1200" placeholder="Es. rispondi sempre con un elenco puntato e cita le fonti">${esc(t.instructions || "")}</textarea></label>`;
  }

  function readTuning(rowEl) {
    const value = (key) => rowEl.querySelector(`[data-t="${key}"]`).value.trim();
    const number = (key) => (value(key) === "" ? null : Number(value(key)));
    return { temperature: number("temperature"), max_tokens: number("max_tokens"), timeout: number("timeout"), instructions: value("instructions") };
  }

  function stats(c) {
    const st = c.stats;
    if (!st || !st.calls) return '<div class="faint" style="font-size:11px">Nessuna chiamata da quando Atena è stata avviata.</div>';
    const color = st.success >= 95 ? "var(--green)" : st.success >= 70 ? "var(--amber)" : "var(--red)";
    return `<div class="faint" style="font-size:11px">${st.calls} chiamate · <b style="color:${color}">${st.success}% riuscite</b> · ~${(st.avg_ms / 1000).toFixed(1)} s
      ${st.last_model ? ` · ultimo: ${esc(st.last_model)}` : ""}</div>${st.last_error ? `<div class="as-error">Ultimo errore: ${esc(st.last_error)}</div>` : ""}`;
  }

  function editor(c) {
    const roles = [["", `Predefinito — ${roleName(c.default_role)}`], ...data.roles.map((r) => [r.id, `${r.icon} ${r.label}`])];
    const options = roles.map(([v, l]) => `<option value="${v}" ${draft.role === v ? "selected" : ""}>${esc(l)}</option>`).join("");
    const group = `mode-${esc(c.id)}`;
    return `<div class="as-edit">
      <label>Lista di riserva (ruolo)<select data-role>${options}</select></label>
      <div class="as-sub">Cervelli dedicati, in ordine di priorità</div>${ownList()}
      <div class="as-add"><select data-pick><option value="">Aggiungi un modello o un server…</option>${pickOptions()}</select><button class="btn sm" data-add>+ Aggiungi</button></div>
      <label class="as-mode"><input type="radio" name="${group}" value="first" ${draft.mode !== "only" ? "checked" : ""}> Prima i miei, poi la lista del ruolo se non rispondono</label>
      <label class="as-mode"><input type="radio" name="${group}" value="only" ${draft.mode === "only" ? "checked" : ""}> Solo i miei, nessun ripiego</label>
      ${tuningFields()}
      <div class="actions"><button class="btn primary sm" data-save>Salva</button><button class="btn sm" data-cancel>Annulla</button>
      <button class="btn sm danger" data-reset>Torna al predefinito</button></div></div>`;
  }

  function row(c) {
    const t = c.assignment.tuning || {};
    const tuned = t.temperature !== null && t.temperature !== undefined || t.max_tokens || t.timeout || t.instructions;
    const custom = c.assignment.role || c.assignment.order.length || tuned;
    return `<div class="as-row ${custom ? "custom" : ""}" data-id="${esc(c.id)}">
      <div class="as-main"><div class="as-name">${esc(c.label)} ${custom ? '<span class="badge">personalizzato</span>' : ""}
        <span class="as-side">${c.side === "core" ? "Core" : "Supervisore"}</span></div>
        <div class="faint">${esc(c.hint)}</div>
        <div class="as-chain">${chips(c.chain)}</div>${stats(c)}</div>
      <button class="btn sm" data-edit-open>${editing === c.id ? "Chiudi" : "Cambia"}</button>
      ${editing === c.id ? editor(c) : ""}</div>`;
  }

  function keepPanel() {
    const refs = [...new Set([...data.components.flatMap((c) => c.chain.slice(0, 2).map((x) => x.ref)), ...Object.keys(keep.overrides)])];
    const rows = refs.map((ref) => `<div class="as-keep"><span class="mono">${esc(label(ref))}</span><select data-keep="${esc(ref)}">${KEEP.map(([v, l]) => `<option value="${v}" ${(keep.overrides[ref] || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select></div>`).join("");
    return `<div class="panel-title" style="margin:0">Permanenza in Memoria RAM / VRAM</div>
      <div class="dim" style="font-size:13px; margin:4px 0 16px">Definisce quanto a lungo ciascun modello resta caricato dopo l'ultima risposta: mantenendolo caricato, Atena risponde istantaneamente senza dover ricaricare i pesi dal disco.</div>${rows || '<div class="faint">Nessun modello attualmente in memoria.</div>'}`;
  }

  function render() {
    const groups = [...new Set(data.components.map((c) => c.group))];
    const body = groups.map((g) => `<div class="as-group"><div class="as-group-title">${esc(g)}</div>${data.components.filter((c) => c.group === g).map(row).join("")}</div>`).join("");
    $("br-assign").innerHTML = `<div class="panel"><div class="panel-title" style="margin:0">Mappatura Cervelli per Singolo Componente</div>
      <div class="dim" style="font-size:13px; margin:4px 0 16px">Ogni agente e funzione interna di Atena può avere un proprio cervello: un modello locale, un altro computer in rete o un servizio cloud, con priorità e ripiego automatico. Ciò che non personalizzi segue la catena predefinita del suo ruolo.</div>${body}</div>
      <div class="panel">${keepPanel()}</div>`;
  }

  async function load() {
    try {
      [data, keep] = await Promise.all([A.api("GET", "/api/brains/assignments"), A.api("GET", "/api/brains/keepalive")]);
    } catch (e) { $("br-assign").innerHTML = `<div class="faint">${esc(e.message)}</div>`; return; }
    render();
  }

  async function save(id, value) {
    try {
      const r = await A.api("PUT", "/api/brains/assignments", { updates: { [id]: value } });
      data.components = r.components; editing = null; draft = null; render();
      A.toast("Assegnazione salvata: già attiva");
    } catch (e) { A.toast(e.message, true); }
  }

  function swap(i, j) { [draft.order[i], draft.order[j]] = [draft.order[j], draft.order[i]]; render(); }

  function onClick(e) {
    const rowEl = e.target.closest(".as-row"); if (!rowEl) return;
    const id = rowEl.dataset.id, c = data.components.find((x) => x.id === id), t = e.target;
    if (t.closest("[data-edit-open]")) {
      editing = editing === id ? null : id;
      draft = editing ? { role: c.assignment.role, order: [...c.assignment.order], mode: c.assignment.mode === "only" ? "only" : "first",
        tuning: { ...(c.assignment.tuning || {}) } } : null;
      return render();
    }
    if (editing !== id) return;
    if (t.closest("[data-t]")) return;
    if (t.dataset.up !== undefined) swap(+t.dataset.up - 1, +t.dataset.up);
    else if (t.dataset.down !== undefined) swap(+t.dataset.down, +t.dataset.down + 1);
    else if (t.dataset.rm !== undefined) { draft.order.splice(+t.dataset.rm, 1); render(); }
    else if (t.dataset.add !== undefined) { const v = rowEl.querySelector("[data-pick]").value; if (v) { draft.order.push(v); render(); } }
    else if (t.dataset.cancel !== undefined) { editing = null; draft = null; render(); }
    else if (t.dataset.reset !== undefined) save(id, null);
    else if (t.dataset.save !== undefined) {
      const mode = rowEl.querySelector(`input[name="mode-${id}"]:checked`);
      save(id, { role: rowEl.querySelector("[data-role]").value, order: draft.order, mode: draft.order.length ? (mode ? mode.value : "first") : "inherit",
        tuning: readTuning(rowEl) });
    }
  }

  async function onChange(e) {
    const ref = e.target.dataset && e.target.dataset.keep; if (ref === undefined) return;
    try {
      keep = await A.api("PUT", "/api/brains/keepalive", { changes: { [ref]: e.target.value || null } });
      A.toast(e.target.value ? "Il modello resterà in memoria per quel tempo dopo l'ultima risposta" : "Permanenza tornata predefinita");
    } catch (err) { A.toast(err.message, true); }
  }

  function init() {
    $("br-assign").addEventListener("click", onClick);
    $("br-assign").addEventListener("change", onChange);
  }

  A.brainAssign = { init, load };
})();
