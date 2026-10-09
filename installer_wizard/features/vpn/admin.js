(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const VPN = (window.AtenaVpn = window.AtenaVpn || {});
  const KINDS = { wireguard: "WireGuard", openvpn: "OpenVPN", ipsec: "IPsec IKEv2", tailscale: "Tailscale", zerotier: "ZeroTier" };
  const SPLIT = { all: "tutto il traffico", include: "solo alcune reti", exclude: "tutto tranne alcune reti" };
  let timer = null, peerConfig = "", peerName = "";

  function stateBadge(p) {
    const s = p.status || {};
    if (s.connected) return `<span class="badge">collegata${s.ip ? ` · ${fmt.esc(s.ip)}` : ""}</span>`;
    if (p.wanted) return `<span class="badge warn">${s.error ? `errore: ${fmt.esc(s.error)}` : "collegamento in corso"}${s.retry_at ? ` · nuovo tentativo alle ${new Date(s.retry_at * 1000).toLocaleTimeString()}` : ""}</span>`;
    return '<span class="badge">scollegata</span>';
  }

  function peers(p) {
    if (p.kind !== "wireguard" || p.role !== "server") return "";
    const rows = (p.settings.peers || []).map((d) => `<div class="vpn-peer"><span>📱 ${fmt.esc(d.name)}</span>
      <span class="mono faint">${fmt.esc(d.address)}</span>
      <button class="btn sm" data-peer-show="${fmt.esc(d.id)}" data-peer-name="${fmt.esc(d.name)}">QR e file</button>
      <button class="btn sm danger" data-peer-del="${fmt.esc(d.id)}">Rimuovi</button></div>`);
    return `<div class="vpn-peers"><b>Dispositivi che possono entrare</b>${rows.join("") || '<div class="faint">Nessun dispositivo.</div>'}
      <form class="vpn-inline" data-peer-add><input name="name" placeholder="es. Telefono di Nunzio" maxlength="32" required>
      <button class="btn sm primary" type="submit">Aggiungi dispositivo</button></form>
      <div class="faint">Apri sul router la porta UDP ${p.settings.listen_port} verso Atena e usa l'indirizzo ${fmt.esc(p.settings.public_host)}.</div></div>`;
  }

  function card(p) {
    const missing = VPN.data && VPN.data.tools && !VPN.data.tools[p.kind];
    return `<div class="panel vpn-card" data-id="${fmt.esc(p.id)}">
      <div class="vpn-top"><div><b>${fmt.esc(p.name)}</b> <span class="faint">${fmt.esc(KINDS[p.kind] || p.kind)}${p.role === "server" ? " · server" : ""} · ${fmt.esc(p.interface)}</span></div>
        ${stateBadge(p)}</div>
      ${missing ? `<div class="badge warn">programma ${fmt.esc(KINDS[p.kind])} non installato su questo server</div>` : ""}
      <div class="vpn-opts">
        <label class="switch"><input type="checkbox" data-opt="autostart" ${p.autostart ? "checked" : ""}> all'avvio</label>
        ${["wireguard", "openvpn", "ipsec"].includes(p.kind) && p.role === "client" ? `<label class="switch"><input type="checkbox" data-opt="kill_switch" ${p.kill_switch ? "checked" : ""}> kill switch</label>` : ""}
        <label class="switch"><input type="checkbox" data-opt="block_dns_leaks" ${p.block_dns_leaks ? "checked" : ""}> blocco fughe DNS</label>
        <span class="faint">${fmt.esc(SPLIT[p.split.mode])}${p.split.networks.length ? `: ${fmt.esc(p.split.networks.join(", "))}` : ""}</span>
      </div>
      ${p.public_key && p.role === "client" ? `<div class="faint">Chiave pubblica: <span class="mono" data-no-i18n>${fmt.esc(p.public_key)}</span></div>` : ""}
      ${peers(p)}
      <div class="actions">${p.wanted ? '<button class="btn sm" data-act="disconnect">Scollega</button>' : '<button class="btn sm primary" data-act="connect">Collega</button>'}
        <button class="btn sm danger" data-act="delete">Elimina</button></div></div>`;
  }

  VPN.render = (d) => {
    if (!d || !d.profiles) return;
    VPN.data = d;
    const tools = Object.entries(d.tools || {}).map(([k, ok]) => `<span class="badge ${ok ? "" : "warn"}">${fmt.esc(KINDS[k])}: ${ok ? "pronto" : "non installato"}</span>`);
    $("vpn-tools").innerHTML = tools.join(" ");
    $("vpn-guard").textContent = d.guard_error ? `Protezioni di rete non applicate: ${d.guard_error}` : "";
    $("vpn-list").innerHTML = d.profiles.map(card).join("") || '<div class="panel faint">Nessuna VPN. Crea un server per entrare in casa da fuori o importa la VPN del lavoro.</div>';
  };

  async function load() {
    try { VPN.render(await A.api("GET", "/api/vpn")); } catch (e) { A.toast(e.message, true); }
    clearTimeout(timer);
    timer = setTimeout(() => { if (document.getElementById("tab-vpn").classList.contains("on")) load(); }, 8000);
  }

  async function call(method, url, body) {
    try { const r = await A.api(method, url, body); VPN.render(r); return r; } catch (e) { A.toast(e.message, true); return null; }
  }

  function showPeer(name, config) {
    peerConfig = config; peerName = name;
    $("vpn-peer-title").textContent = `Configurazione per ${name}`;
    $("vpn-peer-config").textContent = config;
    $("vpn-qr").innerHTML = "";
    const draw = () => {
      const qr = window.qrcode(0, "M");
      qr.addData(config); qr.make();
      $("vpn-qr").innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
    };
    if (window.qrcode) draw();
    else {
      const s = document.createElement("script");
      s.src = "/vendor/qrcode.js"; s.onload = draw; s.onerror = () => { $("vpn-qr").textContent = "QR non disponibile: usa il file .conf"; };
      document.head.appendChild(s);
    }
    $("vpn-peer-dialog").showModal();
  }

  function init() {
    $("vpn-list").addEventListener("click", async (e) => {
      const box = e.target.closest("[data-id]"); if (!box) return;
      const url = `/api/vpn/profiles/${encodeURIComponent(box.dataset.id)}`;
      const act = e.target.closest("[data-act]");
      if (act) {
        if (act.dataset.act === "delete" && !confirm("Eliminare questa VPN e le sue chiavi?")) return;
        if (act.dataset.act === "delete") return call("DELETE", url);
        A.toast(act.dataset.act === "connect" ? "Collegamento…" : "Scollegamento…");
        return call("POST", `${url}/${act.dataset.act}`);
      }
      const show = e.target.closest("[data-peer-show]");
      if (show) {
        try { showPeer(show.dataset.peerName, (await A.api("GET", `${url}/peers/${encodeURIComponent(show.dataset.peerShow)}`)).config); }
        catch (err) { A.toast(err.message, true); }
        return;
      }
      const del = e.target.closest("[data-peer-del]");
      if (del && confirm("Togliere l'accesso a questo dispositivo?")) call("DELETE", `${url}/peers/${encodeURIComponent(del.dataset.peerDel)}`);
    });
    $("vpn-list").addEventListener("change", (e) => {
      const opt = e.target.closest("[data-opt]"); if (!opt) return;
      const box = e.target.closest("[data-id]");
      call("PUT", `/api/vpn/profiles/${encodeURIComponent(box.dataset.id)}`, { [opt.dataset.opt]: opt.checked });
    });
    $("vpn-list").addEventListener("submit", async (e) => {
      const form = e.target.closest("[data-peer-add]"); if (!form) return;
      e.preventDefault();
      const box = form.closest("[data-id]");
      try {
        const r = await A.api("POST", `/api/vpn/profiles/${encodeURIComponent(box.dataset.id)}/peers`, { name: form.elements.name.value.trim() });
        showPeer(r.peer.name, r.config); load();
      } catch (err) { A.toast(err.message, true); }
    });
    $("vpn-peer-close").addEventListener("click", () => $("vpn-peer-dialog").close());
    $("vpn-peer-download").addEventListener("click", () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([peerConfig], { type: "text/plain" }));
      a.download = `${peerName.replace(/[^\w-]+/g, "_") || "atena"}.conf`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
    if (VPN.initForm) VPN.initForm();
  }

  A.tab("vpn", { title: "VPN", init, load });
})();
