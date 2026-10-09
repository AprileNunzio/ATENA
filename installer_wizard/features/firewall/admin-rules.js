(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const FW = (window.AtenaFirewall = window.AtenaFirewall || {});
  const ACTIONS = { accept: "consenti", drop: "scarta", reject: "rifiuta", limit: "limita" };
  const DIRECTIONS = { input: "in ingresso", output: "in uscita", forward: "inoltro" };
  const split = (text) => String(text || "").split(/[\s,]+/).filter(Boolean);
  let editing = "";

  function rules(items) {
    const rows = items.map((r) => `<tr class="${r.enabled ? "" : "faint"}">
      <td>${r.priority}</td><td><b>${fmt.esc(ACTIONS[r.action] || r.action)}</b>${r.rate ? `<div class="faint">${fmt.esc(r.rate)}</div>` : ""}</td>
      <td>${fmt.esc(DIRECTIONS[r.direction] || r.direction)}${r.interface ? ` · ${fmt.esc(r.interface)}` : ""}</td>
      <td>${fmt.esc(r.protocol)}${r.ports.length ? ` ${fmt.esc(r.ports.join(", "))}` : ""}</td>
      <td class="mono">${fmt.esc(r.sources.join(", ") || "qualsiasi")}</td><td class="mono">${fmt.esc(r.destinations.join(", ") || "qualsiasi")}</td>
      <td>${fmt.esc(r.comment)}${r.expires ? `<div class="faint">scade ${new Date(r.expires * 1000).toLocaleString()}</div>` : ""}</td>
      <td class="fw-row-actions"><button class="btn sm" data-toggle="${fmt.esc(r.id)}">${r.enabled ? "Disattiva" : "Attiva"}</button>
        <button class="btn sm" data-edit="${fmt.esc(r.id)}">Modifica</button><button class="btn sm danger" data-del="${fmt.esc(r.id)}">Elimina</button></td></tr>`);
    $("fw-rules").innerHTML = rows.length ? `<table class="fw-table"><thead><tr><th>Priorità</th><th>Azione</th><th>Direzione</th><th>Protocollo</th>
      <th>Origini</th><th>Destinazioni</th><th>Nota</th><th></th></tr></thead><tbody>${rows.join("")}</tbody></table>`
      : '<div class="faint">Nessuna regola personalizzata. In lockdown aggiungi qui chi può entrare.</div>';
  }

  function sets(groups) {
    const rows = Object.entries(groups).map(([name, entries]) => `<div class="fw-item" data-set="${fmt.esc(name)}">
      <b class="mono">@${fmt.esc(name)}</b><textarea rows="2">${fmt.esc(entries.join(", "))}</textarea>
      <div class="actions"><button class="btn sm primary" data-set-save>Salva</button><button class="btn sm danger" data-set-del>Elimina</button></div></div>`);
    $("fw-sets").innerHTML = rows.join("") || '<div class="faint">Crea gruppi riutilizzabili (es. @famiglia, @ufficio) con IP, reti e MAC.</div>';
  }

  function blocks(items) {
    const rows = items.map((b) => `<div class="fw-item"><span class="mono">${fmt.esc(b.address)}</span>
      <span class="faint">${b.expires ? `fino alle ${new Date(b.expires * 1000).toLocaleString()}` : "finché non lo sblocchi"} · ${fmt.esc(b.reason)}</span>
      <button class="btn sm" data-unblock="${fmt.esc(b.address)}">Sblocca</button></div>`);
    $("fw-blocks").innerHTML = rows.join("") || '<div class="faint">Nessun indirizzo bloccato.</div>';
  }

  FW.renderExpert = (d) => {
    if (!document.activeElement || !document.activeElement.closest || !document.activeElement.closest("#fw-sets")) sets(d.sets);
    rules(d.rules); blocks(d.blocks);
  };

  function openForm(rule) {
    const f = $("fw-rule-form");
    editing = rule ? rule.id : "";
    f.reset();
    if (rule) {
      for (const key of ["action", "direction", "protocol", "interface", "rate", "priority", "comment"]) f.elements[key].value = rule[key] || f.elements[key].value;
      for (const key of ["sources", "destinations", "ports"]) f.elements[key].value = rule[key].join(", ");
      f.elements.minutes.value = rule.expires ? Math.max(1, Math.round((rule.expires - Date.now() / 1000) / 60)) : 0;
    }
    f.hidden = false;
  }

  function formRule(f) {
    const minutes = parseInt(f.elements.minutes.value, 10) || 0;
    return {
      action: f.elements.action.value, direction: f.elements.direction.value, protocol: f.elements.protocol.value,
      sources: split(f.elements.sources.value), destinations: split(f.elements.destinations.value), ports: split(f.elements.ports.value),
      interface: f.elements.interface.value.trim(), rate: f.elements.rate.value.trim(), comment: f.elements.comment.value,
      priority: parseInt(f.elements.priority.value, 10) || 100, expires: minutes ? Date.now() / 1000 + minutes * 60 : 0,
    };
  }

  FW.initExpert = () => {
    $("fw-rule-new").addEventListener("click", () => openForm(null));
    $("fw-rule-cancel").addEventListener("click", () => { $("fw-rule-form").hidden = true; });
    $("fw-rule-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = formRule(e.target);
      const r = await FW.call(editing ? "PUT" : "POST", editing ? `/api/firewall/rules/${encodeURIComponent(editing)}` : "/api/firewall/rules", body);
      if (r) { e.target.hidden = true; A.toast(r.applied && r.applied.confirm_by ? "Regola applicata: confermala entro 90 secondi" : "Regola salvata"); }
    });
    $("fw-rules").addEventListener("click", (e) => {
      const rule = (id) => FW.data.rules.find((r) => r.id === id);
      const t = e.target.closest("[data-toggle],[data-edit],[data-del]"); if (!t) return;
      if (t.dataset.edit) return openForm(rule(t.dataset.edit));
      if (t.dataset.del) { if (confirm("Eliminare la regola?")) FW.call("DELETE", `/api/firewall/rules/${encodeURIComponent(t.dataset.del)}`); return; }
      const r = rule(t.dataset.toggle);
      FW.call("PUT", `/api/firewall/rules/${encodeURIComponent(r.id)}`, { ...r, enabled: !r.enabled });
    });
    $("fw-set-new").addEventListener("click", () => {
      const name = (prompt("Nome del gruppo (lettere minuscole, numeri e _):") || "").trim().toLowerCase();
      if (name) FW.call("PUT", `/api/firewall/sets/${encodeURIComponent(name)}`, { entries: [] });
    });
    $("fw-sets").addEventListener("click", (e) => {
      const box = e.target.closest("[data-set]"); if (!box) return;
      const url = `/api/firewall/sets/${encodeURIComponent(box.dataset.set)}`;
      if (e.target.closest("[data-set-save]")) FW.call("PUT", url, { entries: split(box.querySelector("textarea").value) });
      if (e.target.closest("[data-set-del]") && confirm("Eliminare il gruppo?")) FW.call("DELETE", url);
    });
    $("fw-block-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      const r = await FW.call("POST", "/api/firewall/blocks", { address: f.elements.address.value.trim(),
        minutes: parseInt(f.elements.minutes.value, 10) || 0, reason: f.elements.reason.value || "dal pannello" });
      if (r) f.reset();
    });
    $("fw-blocks").addEventListener("click", (e) => {
      const b = e.target.closest("[data-unblock]");
      if (b) FW.call("DELETE", `/api/firewall/blocks/${encodeURIComponent(b.dataset.unblock)}`);
    });
    $("fw-preview").addEventListener("click", async () => {
      try { $("fw-script").textContent = (await A.api("GET", "/api/firewall/preview")).script; $("fw-preview-dialog").showModal(); }
      catch (e) { A.toast(e.message, true); }
    });
    $("fw-preview-close").addEventListener("click", () => $("fw-preview-dialog").close());
  };
})();
