(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const FW = (window.AtenaFirewall = window.AtenaFirewall || {});
  const MODES = { off: "Spento", monitor: "Solo monitoraggio", protect: "Protezione", lockdown: "Lockdown" };
  const LEVELS = { low: "bassa", medium: "media", high: "alta", critical: "critica" };
  const KINDS = { port_scan: "scansione delle porte", host_sweep: "scansione della rete", syn_flood: "SYN flood",
    brute_force: "tentativi di accesso", arp_spoof: "ARP spoofing", dns_tunnel: "tunnel DNS",
    icmp_flood: "flood ICMP", exfiltration: "invio massiccio di dati" };
  let timer = null;

  const list = (items) => (items || []).join(", ");
  const split = (text) => String(text || "").split(/[\s,]+/).filter(Boolean);
  const when = (s) => new Date(s * 1000).toLocaleString();
  const size = (b) => (b > 1e9 ? `${(b / 1e9).toFixed(1)} GB` : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round((b || 0) / 1e3)} kB`);

  FW.call = async (method, url, body) => {
    try { const r = await A.api(method, url, body); FW.render(r); return r; }
    catch (e) { A.toast(e.message, true); return null; }
  };

  function status(d) {
    const s = d.status || {};
    const applied = !s.available ? "nftables non disponibile su questo sistema"
      : s.ok ? `regole applicate alle ${new Date(s.at * 1000).toLocaleTimeString()}` : `errore: ${s.error || "non applicato"}`;
    $("fw-status").innerHTML = `<b>${fmt.esc(MODES[d.policy.mode] || d.policy.mode)}</b>
      <span class="badge ${s.ok ? "" : "warn"}">${fmt.esc(applied)}</span>
      <span class="badge ${d.engine && d.engine.connected ? "" : "warn"}">${d.engine && d.engine.connected ? "analisi del traffico attiva" : "analisi del traffico non collegata"}</span>
      <span class="faint">${d.rules.length} regole · ${d.blocks.length} blocchi · ${Object.keys(d.sets).length} gruppi</span>`;
    document.querySelectorAll("#fw-modes [data-mode]").forEach((b) => b.classList.toggle("primary", b.dataset.mode === d.policy.mode));
    const pending = s.confirm_by && s.confirm_by > Date.now() / 1000;
    $("fw-confirm").hidden = !pending;
    if (pending) $("fw-confirm-text").textContent = `Conferma entro ${Math.max(0, Math.round(s.confirm_by - Date.now() / 1000))} s, altrimenti torno alla configurazione precedente.`;
  }

  function policy(p) {
    if (document.activeElement && document.activeElement.closest && document.activeElement.closest(".fw-form")) return;
    $("fw-lan").checked = p.allow_lan; $("fw-ping").checked = p.allow_ping; $("fw-auto").checked = p.auto_block;
    $("fw-sev").value = p.auto_block_severity; $("fw-minutes").value = p.auto_block_minutes;
    $("fw-ai").checked = p.ai_analysis; $("fw-ai-auto").checked = p.ai_auto_apply;
    $("fw-conf").value = p.ai_min_confidence; $("fw-conf-v").textContent = `${Math.round(p.ai_min_confidence * 100)}%`;
    $("fw-admin-ports").value = list(p.admin_ports); $("fw-trusted").value = list(p.trusted);
  }

  function traffic(sum) {
    if (!sum || !sum.at) {
      $("fw-stats").innerHTML = '<span class="faint">Nessun dato: avvia il servizio atena-netguard per analizzare ethernet e wifi.</span>';
      $("fw-talkers").innerHTML = "";
      return;
    }
    $("fw-stats").innerHTML = `<span><b>${(sum.packets || 0).toLocaleString()}</b> pacchetti</span>
      <span><b>${size(sum.bytes)}</b> analizzati</span><span><b>${sum.flows || 0}</b> flussi attivi</span>`;
    const rows = (sum.top_talkers || []).map((t) => `<tr><td class="mono">${fmt.esc(t.host)}</td><td>${size(t.bytes_out)}</td>
      <td>${size(t.bytes_in)}</td><td>${t.flows}</td><td><button class="btn sm danger" data-block="${fmt.esc(t.host)}">Blocca</button></td></tr>`);
    $("fw-talkers").innerHTML = rows.length ? `<table class="fw-table"><thead><tr><th>Dispositivo</th><th>Inviati</th><th>Ricevuti</th>
      <th>Flussi</th><th></th></tr></thead><tbody>${rows.join("")}</tbody></table>` : "";
  }

  function alerts(items) {
    const rows = (items || []).slice().reverse().map((a) => `<div class="fw-item sev-${fmt.esc(a.severity)}">
      <div><b>${fmt.esc(KINDS[a.kind] || a.kind)}</b> · gravità ${fmt.esc(LEVELS[a.severity] || a.severity)} · <span class="mono">${fmt.esc(a.src)}</span> → <span class="mono">${fmt.esc(a.dst)}</span></div>
      <div class="faint">${fmt.esc(a.detail)} · ${when(a.at)}</div>
      <button class="btn sm danger" data-block="${fmt.esc(a.src)}">Blocca</button></div>`);
    $("fw-alerts").innerHTML = rows.join("") || '<div class="faint">Nessun allarme: la rete è tranquilla.</div>';
  }

  function action(a, i) {
    const what = a.type === "block" ? `blocca ${a.target} per ${a.minutes} min`
      : a.type === "rate_limit" ? `limita ${a.target} a ${a.rate}` : `chiudi la porta ${a.port}/${a.protocol}`;
    return `<label class="fw-action"><input type="checkbox" data-action="${i}" checked> ${fmt.esc(what)}
      ${a.why ? `<span class="faint">— ${fmt.esc(a.why)}</span>` : ""}</label>`;
  }

  function reports(items) {
    const rows = (items || []).slice().reverse().map((r) => `<div class="fw-item sev-${fmt.esc(r.threat_level)}" data-report="${fmt.esc(r.id)}">
      <div><b>${r.attack ? "Attacco probabile" : "Nessun attacco evidente"}</b> · minaccia ${fmt.esc(LEVELS[r.threat_level] || r.threat_level)} · confidenza ${Math.round(r.confidence * 100)}%</div>
      <div>${fmt.esc(r.summary)}</div>
      ${(r.advice || []).map((x) => `<div class="faint">• ${fmt.esc(x)}</div>`).join("")}
      ${r.status === "pending" && r.actions.length ? `${r.actions.map(action).join("")}
        <div class="actions"><button class="btn sm primary" data-approve="1">Applica le scelte</button><button class="btn sm" data-approve="0">Ignora</button></div>`
        : `<div class="faint">${fmt.esc(r.status === "pending" ? "nessuna azione proposta" : r.status)}</div>`}
    </div>`);
    $("fw-reports").innerHTML = rows.join("") || '<div class="faint">Ancora nessuna analisi.</div>';
  }

  FW.render = (d) => {
    if (!d || !d.policy) return;
    FW.data = { ...(FW.data || {}), ...d };
    const full = FW.data;
    status(full); policy(full.policy); traffic(full.summary); alerts(full.alerts); reports(full.reports);
    if (FW.renderExpert) FW.renderExpert(full);
  };

  async function load() {
    try { FW.render(await A.api("GET", "/api/firewall")); } catch (e) { A.toast(e.message, true); }
    clearTimeout(timer);
    timer = setTimeout(() => { if (document.getElementById("tab-firewall").classList.contains("on")) load(); }, 5000);
  }

  function savePolicy() {
    return FW.call("PUT", "/api/firewall/policy", {
      allow_lan: $("fw-lan").checked, allow_ping: $("fw-ping").checked, auto_block: $("fw-auto").checked,
      auto_block_severity: $("fw-sev").value, auto_block_minutes: parseInt($("fw-minutes").value, 10) || 60,
      ai_analysis: $("fw-ai").checked, ai_auto_apply: $("fw-ai-auto").checked,
      ai_min_confidence: parseFloat($("fw-conf").value), admin_ports: split($("fw-admin-ports").value),
      trusted: split($("fw-trusted").value),
    });
  }

  function init() {
    $("fw-modes").addEventListener("click", (e) => {
      const b = e.target.closest("[data-mode]"); if (!b) return;
      if (b.dataset.mode === "lockdown" && !confirm("Lockdown: verrà accettato solo il traffico autorizzato. Hai 90 secondi per confermare. Procedo?")) return;
      FW.call("PUT", "/api/firewall/policy", { mode: b.dataset.mode });
    });
    $("fw-save-policy").addEventListener("click", savePolicy);
    $("fw-conf").addEventListener("input", () => { $("fw-conf-v").textContent = `${Math.round(parseFloat($("fw-conf").value) * 100)}%`; });
    $("fw-confirm-ok").addEventListener("click", async () => { try { await A.api("POST", "/api/firewall/confirm"); A.toast("Modifica confermata"); load(); } catch (e) { A.toast(e.message, true); } });
    $("fw-confirm-undo").addEventListener("click", () => FW.call("POST", "/api/firewall/rollback"));
    $("fw-rollback").addEventListener("click", () => { if (confirm("Tornare alla configurazione precedente?")) FW.call("POST", "/api/firewall/rollback"); });
    $("fw-analyze").addEventListener("click", async () => {
      A.toast("Analisi in corso…");
      try { await A.api("POST", "/api/firewall/analyze"); load(); } catch (e) { A.toast(e.message, true); }
    });
    $("fw-reports").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-approve]"); if (!b) return;
      const box = b.closest("[data-report]");
      const chosen = [...box.querySelectorAll("[data-action]")].filter((c) => c.checked).map((c) => parseInt(c.dataset.action, 10));
      try { await A.api("POST", `/api/firewall/reports/${encodeURIComponent(box.dataset.report)}`, { approve: b.dataset.approve === "1", actions: chosen }); load(); }
      catch (err) { A.toast(err.message, true); }
    });
    document.getElementById("tab-firewall").addEventListener("click", (e) => {
      const b = e.target.closest("[data-block]"); if (!b) return;
      if (confirm(`Bloccare ${b.dataset.block} per 60 minuti?`)) FW.call("POST", "/api/firewall/blocks", { address: b.dataset.block, minutes: 60, reason: "dal pannello" });
    });
    if (FW.initExpert) FW.initExpert();
  }

  A.tab("firewall", { title: "Firewall", init, load });
})();
