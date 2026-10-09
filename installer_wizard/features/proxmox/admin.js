(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const STATES = { running: "acceso", stopped: "spento", paused: "in pausa", suspended: "sospeso" };
  const LABELS = { start: "Avvia", shutdown: "Spegni", stop: "Arresto forzato", reboot: "Riavvia", suspend: "Sospendi", resume: "Riprendi" };
  let data = null;

  const pct = (used, total) => (total ? Math.round((100 * (used || 0)) / total) : 0);
  const gb = (bytes) => `${((bytes || 0) / 1073741824).toFixed(1)} GB`;
  const uptime = (s) => (s ? `${Math.floor(s / 86400)} g ${Math.floor((s % 86400) / 3600)} h` : "—");
  const bar = (value) => `<div class="px-bar"><i style="width:${Math.min(100, value)}%"></i></div>`;

  function actions(g) {
    const list = g.status === "running" ? ["shutdown", "reboot", "suspend", "stop"] : g.status === "paused" || g.status === "suspended" ? ["resume", "stop"] : ["start"];
    return list.map((a) => `<button class="btn sm ${a === "stop" ? "danger" : a === "start" ? "primary" : ""}" data-act="${a}">${fmt.esc(LABELS[a])}</button>`).join("")
      + '<button class="btn sm" data-act="snapshot">Snapshot</button>';
  }

  function render() {
    if (!data) return;
    if (!data.configured) {
      $("px-status").textContent = "Proxmox non è configurato: inserisci indirizzo, utente e password o token API nelle impostazioni di questa funzionalità.";
      $("px-nodes").innerHTML = ""; $("px-guests").innerHTML = "";
      return;
    }
    if (data.error) {
      $("px-status").innerHTML = `<span class="badge warn">${fmt.esc(data.host)}: ${fmt.esc(data.error)}</span>`;
      $("px-nodes").innerHTML = ""; $("px-guests").innerHTML = "";
      return;
    }
    $("px-status").textContent = `Collegato a ${data.host}: ${data.nodes.length} nodi, ${data.guests.length} VM e container.`;
    $("px-nodes").innerHTML = data.nodes.map((n) => `<div class="panel px-node">
      <div class="row" style="justify-content:space-between"><b>${fmt.esc(n.node)}</b><span class="badge ${n.status === "online" ? "" : "warn"}">${fmt.esc(n.status)}</span></div>
      <div class="faint">CPU ${pct(n.cpu, 1)}% di ${n.maxcpu || "?"} core</div>${bar(pct(n.cpu, 1))}
      <div class="faint">RAM ${gb(n.mem)} di ${gb(n.maxmem)}</div>${bar(pct(n.mem, n.maxmem))}
      <div class="faint">acceso da ${uptime(n.uptime)}</div></div>`).join("");
    const q = ($("px-q").value || "").toLowerCase();
    const rows = data.guests.filter((g) => !q || String(g.vmid).includes(q) || String(g.name || "").toLowerCase().includes(q)).map((g) => `<tr data-node="${fmt.esc(g.node)}" data-kind="${fmt.esc(g.type)}" data-vmid="${g.vmid}">
      <td class="mono">${g.vmid}</td><td>${g.type === "lxc" ? "📦" : "🖥"} ${fmt.esc(g.name || "")}</td><td>${fmt.esc(g.node)}</td>
      <td><span class="badge ${g.status === "running" ? "" : "warn"}">${fmt.esc(STATES[g.status] || g.status)}</span></td>
      <td>${pct(g.cpu, 1)}%</td><td>${gb(g.mem)} / ${gb(g.maxmem)}</td><td class="px-actions">${actions(g)}</td></tr>`);
    $("px-guests").innerHTML = rows.length ? `<table class="px-table"><thead><tr><th>ID</th><th>Nome</th><th>Nodo</th><th>Stato</th><th>CPU</th><th>RAM</th><th></th></tr></thead>
      <tbody>${rows.join("")}</tbody></table>` : '<div class="faint">Nessuna VM o container.</div>';
  }

  async function load() {
    $("px-status").textContent = "Collegamento a Proxmox…";
    try { data = await A.api("GET", "/api/proxmox"); render(); } catch (e) { A.toast(e.message, true); }
  }

  function init() {
    $("px-refresh").addEventListener("click", load);
    $("px-q").addEventListener("input", render);
    $("px-guests").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]"); if (!b) return;
      const row = b.closest("[data-vmid]");
      const base = `/api/proxmox/${encodeURIComponent(row.dataset.node)}/${row.dataset.kind}/${row.dataset.vmid}`;
      try {
        if (b.dataset.act === "snapshot") {
          const name = (prompt("Nome dello snapshot (lettere, numeri, - e _):", `atena-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}`) || "").trim();
          if (!name) return;
          await A.api("POST", `${base}/snapshot`, { name });
        } else {
          if (["stop", "shutdown", "reboot"].includes(b.dataset.act) && !confirm(`${LABELS[b.dataset.act]} ${row.dataset.kind} ${row.dataset.vmid}?`)) return;
          await A.api("POST", `${base}/${b.dataset.act}`);
        }
        A.toast("Comando inviato a Proxmox");
        setTimeout(load, 2500);
      } catch (err) { A.toast(err.message, true); }
    });
  }

  A.tab("proxmox", { title: "Gestione Proxmox", init, load });
})();
