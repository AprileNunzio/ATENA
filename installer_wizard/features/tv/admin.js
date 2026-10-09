(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  let page = 1, total = 0, selected = null, player = null, targets = [];
  const KIND = { display: "🖥", pc: "💻", cast: "📡", dlna: "📺" };

  function playerLib() {
    if (window.AtenaTv) return Promise.resolve();
    return new Promise((ok, fail) => { const s = document.createElement("script"); s.src = "/static/shared/tvplayer.js"; s.onload = ok; s.onerror = () => fail(new Error("Lettore non disponibile")); document.head.appendChild(s); });
  }

  async function loadOverview() {
    const d = await A.api("GET", "/api/tv");
    $("tv-lists").innerHTML = d.playlists.map((p) => `<div class="tv-list" data-pid="${fmt.esc(p.id)}"><div><b>${fmt.esc(p.name)}</b>
      <div class="faint">${p.count} canali · ${p.source === "url" ? "da indirizzo" : "da file"}${p.refreshed_at ? ` · aggiornata ${new Date(p.refreshed_at * 1000).toLocaleString()}` : ""}</div>
      ${p.error ? `<div style="color:var(--amber); font-size:12px">${fmt.esc(p.error)}</div>` : ""}</div>
      <div class="actions">${p.has_url ? '<button type="button" class="btn sm" data-refresh>⟳</button>' : ""}<button type="button" class="btn sm danger" data-drop>✕</button></div></div>`).join("")
      || '<div class="muted-note">Nessuna playlist ancora.</div>';
    const g = $("tv-group").value;
    $("tv-group").innerHTML = '<option value="">Tutti i gruppi</option>' + d.groups.map((x) => `<option ${x === g ? "selected" : ""}>${fmt.esc(x)}</option>`).join("");
    $("tv-count").textContent = d.count ? `(${d.count})` : "";
  }

  async function loadChannels() {
    const q = new URLSearchParams({ q: $("tv-q").value, group: $("tv-group").value, fav: $("tv-fav").checked, page });
    const d = await A.api("GET", `/api/tv/channels?${q}`);
    total = d.total;
    $("tv-grid").innerHTML = d.channels.map((c) => `<div class="tv-ch ${selected === c.id ? "on" : ""}" data-cid="${fmt.esc(c.id)}" data-name="${fmt.esc(c.name)}">
      <span class="tv-logo">${fmt.esc(c.name.slice(0, 2).toUpperCase())}</span><div class="tv-ch-nm"><b>${fmt.esc(c.name)}</b><span class="faint">${fmt.esc(c.group)}</span></div>
      <button type="button" class="tv-star ${c.favorite ? "on" : ""}" data-star title="Preferito">★</button></div>`).join("")
      || '<div class="muted-note">Nessun canale: aggiungi una playlist qui sopra.</div>';
    $("tv-page").textContent = total ? `${page} / ${Math.max(1, Math.ceil(total / 60))}` : "";
    $("tv-chlist").innerHTML = d.channels.slice(0, 60).map((c) => `<option value="${fmt.esc(c.name)}">`).join("");
  }

  async function loadTargets(discover = false) {
    try { targets = (await A.api("GET", `/api/tv/targets${discover ? "?discover=true" : ""}`)).targets; } catch (e) { A.toast(e.message, true); return; }
    const opts = targets.map((t) => `<option value="${fmt.esc(t.id)}" ${t.online ? "" : "disabled"}>${KIND[t.kind] || "•"} ${fmt.esc(t.name)}${t.online ? "" : " (spento)"}</option>`).join("");
    $("tv-target").innerHTML = opts; $("tv-rtarget").innerHTML = opts.replace(/ disabled/g, "");
  }

  async function preview(cid, name) {
    selected = cid;
    document.querySelectorAll("#tv-grid .tv-ch").forEach((el) => el.classList.toggle("on", el.dataset.cid === cid));
    $("tv-go").disabled = false;
    $("tv-pmsg").textContent = `${name}: in collegamento…`;
    try {
      const r = await A.api("GET", `/api/tv/preview/${encodeURIComponent(cid)}`);
      await playerLib();
      if (player) player.stop();
      player = await window.AtenaTv.play($("tv-video"), r.src, (s) => { $("tv-pmsg").textContent = s === "playing" ? "" : `${name}: ${s}`; });
    } catch (e) { $("tv-pmsg").textContent = `${name}: ${e.message}`; }
  }

  async function send() {
    if (!selected) return;
    try {
      const r = await A.api("POST", "/api/tv/play", { channel: selected, target: $("tv-target").value });
      $("tv-now").textContent = `In onda ${r.where}.`; A.toast(`Canale inviato ${r.where}`);
    } catch (e) { A.toast(e.message, true); }
  }

  async function addPlaylist(e) {
    e.preventDefault();
    const file = $("tv-file").files[0];
    const body = { name: $("tv-name").value.trim(), url: file ? "" : $("tv-url").value.trim(), text: file ? await file.text() : "" };
    if (!body.url && !body.text) { A.toast("Incolla un indirizzo o scegli un file", true); return; }
    const btn = $("tv-add").querySelector("button.primary"); btn.disabled = true;
    try { const r = await A.api("POST", "/api/tv/playlists", body); A.toast(`${r.count} canali importati`); $("tv-add").reset(); await load(); }
    catch (err) { A.toast(err.message, true); } finally { btn.disabled = false; }
  }

  async function load() {
    try { await loadOverview(); await loadChannels(); } catch (e) { A.toast(e.message, true); }
    loadTargets();
    if (A.tvRules) A.tvRules.load();
  }

  function init() {
    $("tv-add").addEventListener("submit", addPlaylist);
    $("tv-file").addEventListener("change", () => { const f = $("tv-file").files[0]; if (f && !$("tv-name").value) $("tv-name").value = f.name.replace(/\.m3u8?$/i, ""); });
    $("tv-lists").addEventListener("click", async (e) => {
      const row = e.target.closest("[data-pid]"); if (!row) return;
      try {
        if (e.target.closest("[data-refresh]")) { const r = await A.api("POST", `/api/tv/playlists/${row.dataset.pid}/refresh`); A.toast(`${r.count} canali`); }
        if (e.target.closest("[data-drop]")) { if (!confirm("Rimuovere questa playlist e i suoi canali?")) return; await A.api("DELETE", `/api/tv/playlists/${row.dataset.pid}`); }
        load();
      } catch (err) { A.toast(err.message, true); }
    });
    $("tv-grid").addEventListener("click", async (e) => {
      const ch = e.target.closest("[data-cid]"); if (!ch) return;
      if (e.target.closest("[data-star]")) {
        const on = !e.target.classList.contains("on");
        try { await A.api("PUT", `/api/tv/favorites/${ch.dataset.cid}`, { on }); e.target.classList.toggle("on", on); } catch (err) { A.toast(err.message, true); }
        return;
      }
      preview(ch.dataset.cid, ch.dataset.name);
    });
    let timer = null;
    $("tv-q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { page = 1; loadChannels(); }, 250); });
    $("tv-group").addEventListener("change", () => { page = 1; loadChannels(); });
    $("tv-fav").addEventListener("change", () => { page = 1; loadChannels(); });
    $("tv-prev").addEventListener("click", () => { if (page > 1) { page--; loadChannels(); } });
    $("tv-next").addEventListener("click", () => { if (page * 60 < total) { page++; loadChannels(); } });
    $("tv-go").addEventListener("click", send);
    $("tv-scan").addEventListener("click", () => loadTargets(true).then(() => A.toast("Ricerca dispositivi completata")));
    $("tv-stop").addEventListener("click", async () => { try { await A.api("POST", "/api/tv/stop"); $("tv-now").textContent = ""; } catch (e) { A.toast(e.message, true); } });
    if (A.tvRules) A.tvRules.init();
  }

  A.tab("tv", { title: "TV", init, load });
})();
