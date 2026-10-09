(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const ICON = { local: "🖥", server: "🖧", cloud: "☁" };
  const ORIGIN = { local: "Questo server", server: "Server in rete", cloud: "Cloud" };
  const SCOPES = {
    anywhere: "Ovunque, nell'ordine scelto",
    home_first: "Prima in casa, cloud solo di riserva",
    home: "Solo in casa: nessun dato esce",
  };
  const STRATEGIES = { order: "Nell'ordine della lista", fastest: "Il più veloce misurato" };
  let presets = [], sources = null, onSave = null, data = null;
  const builder = {};

  const roleOf = (id) => data.roles.find((r) => r.id === id);
  const short = (ref) => { const e = data.roles.flatMap((r) => r.entries).find((x) => x.name === ref); return e ? e.model : ref.split("/").pop(); };
  const originOf = (ref) => { const e = data.roles.flatMap((r) => r.entries).find((x) => x.name === ref); return e ? e.origin : (ref.startsWith("cloud:") ? "cloud" : "local"); };

  function pipeline(role) {
    if (!role.effective.length) return '<div class="ch-pipe empty">Nessun cervello raggiungibile per questo ruolo: scegli un profilo qui sotto.</div>';
    return `<div class="ch-pipe">${role.effective.map((ref, i) => `${i ? '<span class="ch-arrow">→</span>' : ""}
      <span class="ch-step ${i === 0 ? "first" : ""} o-${originOf(ref)}" title="${fmt.esc(ORIGIN[originOf(ref)])}">
        <span class="ch-ic">${ICON[originOf(ref)] || "•"}</span><span class="ch-nm">${fmt.esc(short(ref))}</span>${i === 0 ? '<span class="ch-tag">risponde</span>' : ""}</span>`).join("")}</div>`;
  }

  function presetRow(role) {
    const custom = role.profile === "custom" ? '<span class="ch-preset on static">🛠 Personalizzato</span>' : "";
    return `<div class="ch-presets">${presets.map((p) => `<button type="button" class="ch-preset ${role.profile === p.id ? "on" : ""}" data-preset="${p.id}" data-role="${role.id}" title="${fmt.esc(p.hint)}">${p.icon} ${fmt.esc(p.label)}</button>`).join("")}${custom}</div>`;
  }

  function select(attr, map, value, role) {
    return `<select data-${attr}="${role.id}">${Object.entries(map).map(([k, v]) => `<option value="${k}" ${k === value ? "selected" : ""}>${fmt.esc(v)}</option>`).join("")}</select>`;
  }

  function sourceList(kind) {
    if (!sources) return [];
    if (kind === "local") return [sources.local];
    return kind === "server" ? sources.servers : sources.cloud;
  }

  function builderHtml(role) {
    const st = builder[role.id] || (builder[role.id] = { kind: "local", source: "" });
    const list = sourceList(st.kind);
    if (!list.some((s) => s.id === st.source)) st.source = list[0] ? list[0].id : "";
    const src = list.find((s) => s.id === st.source);
    const kinds = ["local", "server", "cloud"].map((k) => `<button type="button" data-kind="${k}" class="${st.kind === k ? "on" : ""}">${ICON[k]} ${ORIGIN[k]}</button>`).join("");
    let body;
    if (!sources) body = '<span class="faint">Carico le sorgenti…</span>';
    else if (!list.length) body = st.kind === "server"
      ? '<span class="faint">Nessun server in rete collegato.</span> <button type="button" class="btn sm" data-goto="servers">Collega un server</button>'
      : '<span class="faint">Nessun servizio cloud collegato.</span> <button type="button" class="btn sm" data-goto="cloud">Collega un servizio</button>';
    else {
      const sourcePick = st.kind === "local" ? "" : `<select data-source="${role.id}">${list.map((s) => `<option value="${fmt.esc(s.id)}" ${s.id === st.source ? "selected" : ""}>${fmt.esc(s.name)}${s.online ? "" : " (offline)"}</option>`).join("")}</select>`;
      const taken = new Set(role.entries.map((e) => e.name));
      const opts = (src ? src.models : []).filter((m) => !taken.has(m.ref)).map((m) => `<option value="${fmt.esc(m.ref)}">${fmt.esc(m.label)}${m.installed === false ? " — da scaricare" : ""}${m.size_gb ? ` · ${m.size_gb} GB` : ""}</option>`).join("");
      body = `${sourcePick}<select data-model="${role.id}">${opts || '<option value="">Nessun altro modello</option>'}</select>
        <button type="button" class="btn sm primary" data-put="first" data-role="${role.id}">In cima</button>
        <button type="button" class="btn sm" data-put="last" data-role="${role.id}">In fondo</button>`;
    }
    return `<div class="ch-builder"><div class="seg" data-kinds="${role.id}">${kinds}</div><div class="ch-builder-row">${body}</div></div>`;
  }

  function entriesHtml(role) {
    const activeRef = role.active && role.active.ref;
    return role.entries.map((m, i) => {
      const st = m.stats, allowed = role.scope !== "home" || m.origin !== "cloud";
      const state = !allowed ? '<span style="color:var(--amber)">escluso dalla privacy</span>'
        : m.available ? '<span style="color:var(--green)">pronto</span>'
        : `<span style="color:var(--amber)">${m.origin === "local" ? "da scaricare" : m.origin === "server" ? "server non raggiungibile" : "chiave mancante"}</span>`;
      const sub = [m.name === activeRef ? '<b style="color:var(--cyan)">• in uso</b>' : "", `${ICON[m.origin]} ${fmt.esc(m.provider)}`, state,
        st ? `${st.ok} risposte · ~${(st.avg_ms / 1000).toFixed(1)} s${st.fail ? ` · ${st.fail} errori` : ""}` : ""].filter(Boolean).join(" · ");
      return A.prioItem(m.name, i, m.model, sub, !m.available || !allowed, false);
    }).join("") || '<div class="muted-note">Lista automatica: aggiungi un passo qui sotto per personalizzarla.</div>';
  }

  function card(role) {
    return `<div class="ch-card" data-card="${role.id}">
      <div class="ch-card-head"><div class="ch-title">${role.icon} ${fmt.esc(role.label)}</div><div class="muted-note">${fmt.esc(role.hint)}</div></div>
      ${pipeline(role)}
      ${presetRow(role)}
      <div class="x-expert ch-expert">
        <div class="ch-settings">
          <label>Dove può pensare ${select("scope", SCOPES, role.scope, role)}</label>
          <label>Chi risponde per primo ${select("strategy", STRATEGIES, role.strategy, role)}</label>
        </div>
        <div class="ch-sub">Catena di ripiego <span class="faint">— trascina per riordinare, ✕ per togliere</span></div>
        <div class="prio" data-prio="${role.id}">${entriesHtml(role)}</div>
        <div class="ch-sub">Aggiungi un passo</div>
        ${builderHtml(role)}
        <div class="actions"><button type="button" class="btn sm" data-preset="auto" data-role="${role.id}">Ripristina automatico</button>
          <button type="button" class="btn sm" data-goto="agents">Agenti e componenti →</button></div>
      </div></div>`;
  }

  function render(d) {
    data = d;
    const host = $("br-roles");
    if (!host) return;
    host.innerHTML = d.roles.map(card).join("");
    host.querySelectorAll("[data-prio]").forEach((list) => A.makeSortable(list, (items) => onSave({ [list.dataset.prio]: items })));
    $("ch-all").innerHTML = presets.map((p) => `<button type="button" data-all="${p.id}" title="${fmt.esc(p.hint)}">${p.icon} ${fmt.esc(p.label)}</button>`).join("");
  }

  async function applyPreset(presetId, roles) {
    try {
      const d = await A.api("POST", "/api/brains/preset", { preset: presetId, roles });
      A.brain.set(d);
      const p = presets.find((x) => x.id === presetId);
      A.toast(`Profilo «${p ? p.label : presetId}» applicato`);
    } catch (e) { A.toast(e.message, true); }
  }

  async function saveSettings(roleId, body) {
    try { A.brain.set(await A.api("PUT", `/api/brains/settings/${roleId}`, body)); } catch (e) { A.toast(e.message, true); }
  }

  async function loadSources(refresh = false) {
    if (sources && !refresh) return;
    try { sources = await A.api("GET", "/api/brains/sources"); } catch (e) { A.toast(e.message, true); return; }
    if (data) render(data);
  }

  function addStep(roleId, where) {
    const role = roleOf(roleId), ref = $("br-roles").querySelector(`[data-model="${roleId}"]`)?.value;
    if (!ref) { A.toast("Scegli prima un modello", true); return; }
    const current = role.custom ? role.entries.map((e) => e.name).filter((n) => n !== ref) : [];
    onSave({ [roleId]: where === "first" ? [ref, ...current] : [...current, ref] });
    const local = sources && sources.local.models.find((m) => m.ref === ref);
    if (local && !local.installed && confirm(`${local.label} non è ancora sul server: scaricarlo ora${local.size_gb ? ` (${local.size_gb} GB)` : ""}?`)) {
      A.api("POST", "/api/models/pull", { name: ref }).then(() => A.toast(`Download di ${ref} avviato`)).catch((e) => A.toast(e.message, true));
    }
  }

  function init(save) {
    onSave = save;
    A.api("GET", "/api/brains/presets").then((r) => { presets = r.presets; if (data) render(data); }).catch((e) => A.toast(e.message, true));
    $("ch-all").addEventListener("click", (e) => {
      const b = e.target.closest("[data-all]");
      if (b && confirm("Applicare questo profilo a tutti i ruoli? Le catene personalizzate verranno sostituite.")) applyPreset(b.dataset.all, null);
    });
    $("ch-refresh").addEventListener("click", () => loadSources(true).then(() => A.toast("Sorgenti aggiornate")));
    const host = $("br-roles");
    host.addEventListener("click", (e) => {
      const t = e.target;
      const preset = t.closest("[data-preset]");
      if (preset) return applyPreset(preset.dataset.preset, [preset.dataset.role]);
      const kind = t.closest("[data-kind]");
      if (kind) { const id = kind.closest("[data-kinds]").dataset.kinds; builder[id] = { kind: kind.dataset.kind, source: "" }; return render(data); }
      const put = t.closest("[data-put]");
      if (put) return addStep(put.dataset.role, put.dataset.put);
      const go = t.closest("[data-goto]");
      if (go) { if (go.dataset.goto === "agents") A.brain.showSubpage("assign"); else { A.brain.showSubpage("add"); A.brain.showSource(go.dataset.goto); } }
    });
    host.addEventListener("change", (e) => {
      const t = e.target;
      if (t.dataset.scope) saveSettings(t.dataset.scope, { scope: t.value });
      if (t.dataset.strategy) saveSettings(t.dataset.strategy, { strategy: t.value });
      if (t.dataset.source) { builder[t.dataset.source].source = t.value; render(data); }
    });
    document.addEventListener("atena:uimode", (e) => { if (e.detail === "expert") loadSources(); });
  }

  A.brainChains = { init, render, loadSources: () => (A.uiMode && A.uiMode.expert() ? loadSources() : Promise.resolve()) };
})();
