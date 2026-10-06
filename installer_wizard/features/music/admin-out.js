(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const mu = A.mu, esc = mu.esc;
  const O = mu.out;
  const ICON = { display: "🖥", cast: "📺", dlna: "🔈", browser: "💻" };
  let timer = null, devices = [], busy = false;

  const stop = () => { clearInterval(timer); timer = null; };

  async function poll() {
    if (!O.remote || busy) return;
    try {
      const view = await mu.get(`/api/music/out/${encodeURIComponent(O.id)}`);
      mu.player.remoteApply(view);
      if (view.error) A.toast(view.error, true);
    } catch (e) { console.info("Stato del dispositivo non letto", e); }
  }

  function watch() {
    stop();
    timer = setInterval(() => { if (O.remote) poll(); else stop(); }, 2000);
  }

  O.start = async (ids, index, start) => {
    busy = true;
    try {
      const view = await mu.post(`/api/music/out/${encodeURIComponent(O.id)}/play`, { tracks: ids, index, start, repeat: mu.player.state().repeat });
      mu.player.remoteApply(view);
    } catch (e) { mu.err(e); } finally { busy = false; }
  };

  O.control = async (action, value) => {
    busy = true;
    try {
      const view = await mu.post(`/api/music/out/${encodeURIComponent(O.id)}/control`, { action, value: value || 0 });
      mu.player.remoteApply(view);
    } catch (e) { mu.err(e); } finally { busy = false; }
  };

  async function toLocal() {
    const view = await mu.get(`/api/music/out/${encodeURIComponent(O.id)}`).catch(() => null);
    try { await O.control("stop"); } catch (e) { console.info(e); }
    stop();
    Object.assign(O, { id: "browser", remote: false, name: "Questo browser" });
    mu.remoteState = null;
    if (view && view.queue && view.queue.length) mu.player.play(view.queue, view.index, { start: view.position || 0 });
    mu.syncPlayer();
    A.toast("Riproduzione tornata in questo browser");
  }

  async function toDevice(device) {
    const { tracks, index } = mu.player.queue();
    const position = mu.player.position();
    const wasLocal = !O.remote;
    if (O.remote && O.id !== device.id) { try { await O.control("stop"); } catch (e) { console.info(e); } }
    Object.assign(O, { id: device.id, remote: true, name: device.name });
    if (wasLocal) mu.player.pauseLocal();
    watch();
    if (tracks.length) await O.start(tracks.map((t) => t.id), index, position);
    mu.syncPlayer();
    A.toast(`Riproduzione su ${device.name}`);
  }

  O.select = async (device) => {
    try {
      if (device.id === "browser") { if (O.remote) await toLocal(); } else await toDevice(device);
      if (mu.view.name === "devices") mu.reload();
    } catch (e) { mu.err(e); }
  };

  async function fetchDevices(refresh) {
    const r = await mu.get(`/api/music/out${refresh ? "?refresh=true" : ""}`);
    devices = r.devices;
    return r;
  }

  O.picker = async (anchor) => {
    let r;
    try { r = await fetchDevices(false); } catch (e) { mu.err(e); return; }
    const items = [{ label: `${ICON.browser} Questo browser${O.remote ? "" : " ✓"}`, fn: () => O.select({ id: "browser", name: "Questo browser" }) },
      ...r.devices.map((d) => ({ label: `${ICON[d.kind] || "▶"} ${d.name}${O.id === d.id ? " ✓" : ""}`, fn: () => O.select(d) })),
      "-", { label: "Cerca altri dispositivi…", fn: async () => { A.toast("Cerco nella rete…"); try { await fetchDevices(true); O.picker(anchor); } catch (e) { mu.err(e); } } },
      { label: "Gestisci i dispositivi", fn: () => mu.go("devices") }];
    mu.menu(anchor, items, r.cast ? "Riproduci su" : "Riproduci su (ricerca in rete disattivata)");
  };

  mu.views.devices = async () => {
    const r = await fetchDevices(false);
    const rows = [{ id: "browser", kind: "browser", name: "Questo browser", model: "Audio di questo computer", active: !O.remote }, ...r.devices];
    $("mu-main").innerHTML = `<h2>Dispositivi</h2><div class="mu-actions"><button class="btn" id="mu-scan">⟳ Cerca nella rete</button></div>
      ${r.cast ? "" : '<div class="mu-note">La ricerca di Chromecast, TV e speaker è disattivata nelle impostazioni di Gestione Musica.</div>'}
      ${rows.map((d) => `<div class="mu-dev ${O.id === d.id ? "on" : ""}"><div class="ic">${ICON[d.kind] || "▶"}</div>
        <div class="nm"><b>${esc(d.name)}</b><small>${d.kind === "browser" ? "Audio di questo computer" : d.kind === "cast" ? `Chromecast ${esc(d.model || "")}` : d.kind === "dlna" ? `Altoparlante o TV (DLNA) ${esc(d.model || "")}` : "Schermo di Atena"}${d.active ? " · in riproduzione" : ""}</small></div>
        ${O.id === d.id ? '<span class="badge ok">in uso</span>' : `<button class="btn sm primary" data-dev="${esc(d.id)}">Riproduci qui</button>`}</div>`).join("")}
      <p class="mu-note">Gli schermi di Atena compaiono quando la pagina del display è aperta. Chromecast, TV e speaker DLNA vengono trovati nella rete locale; se non compaiono, controlla che siano accesi e sulla stessa rete.</p>`;
    $("mu-scan").addEventListener("click", async () => { A.toast("Cerco nella rete…"); try { await fetchDevices(true); mu.reload(); } catch (e) { mu.err(e); } });
    $("mu-main").querySelectorAll("[data-dev]").forEach((b) => b.addEventListener("click", () => {
      const d = rows.find((x) => x.id === b.dataset.dev);
      if (d) O.select(d);
    }));
  };

  O.init = () => {};
})();
