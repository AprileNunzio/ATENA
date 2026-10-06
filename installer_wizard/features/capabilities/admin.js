(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const when = (t) => (t ? new Date(t * 1000).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" }) : "mai");
  let timer = null;

  function snippet(token) {
    return JSON.stringify({ mcpServers: { atena: { url: `${location.origin}/mcp`, headers: { Authorization: `Bearer ${token}` } } } }, null, 2);
  }

  async function tokens() {
    const rows = (await A.api("GET", "/api/mcp/tokens")).tokens;
    $("cp-tokens").innerHTML = rows.length ? rows.map((t) => `<div class="cp-row"><b>${fmt.esc(t.label)}</b>
      <span class="badge ${t.risky ? "bad" : "ok"}">${t.risky ? "anche azioni delicate" : "solo lettura e controllo"}</span>
      <span class="faint">creato ${when(t.created)} · ultimo uso ${when(t.used)}</span>
      <button class="btn sm" data-revoke="${fmt.esc(t.id)}">Revoca</button></div>`).join("") : '<div class="faint">Nessun token: nessun programma esterno può collegarsi.</div>';
  }

  async function servers() {
    const rows = (await A.api("GET", "/api/mcp/servers")).servers;
    $("sv-list").innerHTML = rows.length ? rows.map((s) => `<div class="cp-row"><b>${fmt.esc(s.name)}</b>
      <span class="badge ${s.status === "collegato" ? "ok" : "bad"}">${fmt.esc(s.status)}</span>
      <span class="faint">${s.tools} strumenti · ${fmt.esc(s.url)}${s.trusted ? " · fidato" : ""}${s.enabled ? "" : " · spento"}</span>
      <button class="btn sm" data-refresh="${fmt.esc(s.id)}">Aggiorna</button>
      <button class="btn sm" data-toggle="${fmt.esc(s.id)}" data-on="${s.enabled ? 0 : 1}">${s.enabled ? "Spegni" : "Accendi"}</button>
      <button class="btn sm" data-drop="${fmt.esc(s.id)}">Scollega</button></div>`).join("") : '<div class="faint">Nessun server collegato.</div>';
  }

  async function attach() {
    const body = { name: $("sv-name").value.trim(), url: $("sv-url").value.trim(), token: $("sv-token").value.trim(), trusted: $("sv-trusted").checked };
    const r = await A.api("POST", "/api/mcp/servers", body);
    A.toast(`${r.status}: ${r.tools} strumenti`, r.tools === 0);
    ["sv-name", "sv-url", "sv-token"].forEach((id) => { $(id).value = ""; });
    servers();
  }

  async function serverAction(e) {
    const d = e.target.dataset;
    if (d.refresh) await A.api("POST", `/api/mcp/servers/${encodeURIComponent(d.refresh)}/refresh`);
    else if (d.toggle) await A.api("PUT", `/api/mcp/servers/${encodeURIComponent(d.toggle)}`, { enabled: d.on === "1" });
    else if (d.drop) await A.api("DELETE", `/api/mcp/servers/${encodeURIComponent(d.drop)}`);
    else return;
    servers();
  }

  async function team() {
    const data = await A.api("GET", "/api/team");
    const busy = Object.entries(data.doing);
    $("cp-board").textContent = busy.length ? "Adesso: " + busy.map(([a, v]) => `${a}: ${v.what}`).join(" · ") : "Nessun agente al lavoro in questo momento.";
    $("cp-team").innerHTML = data.agents.map((a) => `<div class="cp-row"><b>${fmt.esc(a.name)}</b>
      <span class="badge">priorità ${a.priority}</span>${a.enabled ? "" : '<span class="badge bad">spento</span>'}
      <span class="faint">${fmt.esc(a.tools.map((t) => t.name).join(", ") || "nessuno strumento diretto")}${a.doing ? " · ora: " + fmt.esc(a.doing) : ""}</span></div>`).join("");
  }

  async function create() {
    const label = $("cp-label").value.trim();
    if (!label) { A.toast("Dai un nome al client", true); return; }
    const made = await A.api("POST", "/api/mcp/tokens", { label, risky: $("cp-risky").checked });
    const box = $("cp-new");
    box.hidden = false;
    box.innerHTML = `<b>Copia ora questa configurazione: il token non verrà più mostrato.</b><pre>${fmt.esc(snippet(made.token))}</pre>`;
    $("cp-label").value = "";
    tokens();
  }

  function init() {
    $("cp-url").textContent = `${location.origin}/mcp`;
    $("cp-create").addEventListener("click", () => create().catch((e) => A.toast(e.message, true)));
    $("sv-add").addEventListener("click", () => attach().catch((e) => A.toast(e.message, true)));
    $("sv-list").addEventListener("click", (e) => serverAction(e).catch((err) => A.toast(err.message, true)));
    $("cp-tokens").addEventListener("click", async (e) => {
      const id = e.target.dataset.revoke;
      if (!id) return;
      await A.api("DELETE", `/api/mcp/tokens/${encodeURIComponent(id)}`);
      A.toast("Token revocato");
      tokens();
    });
  }

  A.tab("capabilities", {
    title: "Squadra e MCP", init,
    load() { tokens(); servers(); team(); clearInterval(timer); timer = setInterval(() => { if (A.isOn("capabilities")) team(); }, 5000); },
    leave() { clearInterval(timer); },
  });
})();
