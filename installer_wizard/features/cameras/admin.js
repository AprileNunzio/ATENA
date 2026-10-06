(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const KIND = { local: "Webcam", ip: "Rete", infrared: "Infrarossi" };
  const C = { data: null, pane: "live", panes: {}, timers: {}, esc: (s) => fmt.esc(s) };
  A.cams = C;

  C.transform = (s) => (s.client_transform ? `transform:rotate(${s.options.rotate}deg)${s.options.mirror ? " scaleX(-1)" : ""}` : "");
  C.kind = (s) => KIND[s.kind] || s.kind;
  C.badge = (text, kind = "") => `<span class="badge ${kind}">${C.esc(text)}</span>`;
  C.bytes = (n) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} kB`);
  C.when = (t) => new Date(t * 1000).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  C.source = (id) => ((C.data || {}).sources || []).find((s) => s.id === id);

  C.reload = async () => {
    try { C.data = await A.api("GET", "/api/cameras/overview"); } catch (e) { A.toast(e.message, true); return null; }
    status();
    return C.data;
  };

  function status() {
    const d = C.data, rows = d.sources;
    const live = rows.filter((s) => s.kind !== "infrared").length;
    const rec = rows.filter((s) => s.record.recording).length;
    const motion = rows.filter((s) => s.options.motion).length;
    const tools = [!d.tools.ffmpeg ? "ffmpeg non installato: serve per le telecamere di rete" : "", !d.tools.v4l2 && !d.problems.some((p) => p.includes("v4l")) ? "v4l-utils non installato: servono per i controlli webcam" : ""].filter(Boolean);
    $("cam-status").innerHTML = `${live} sorgenti video · ${rec} in registrazione · ${motion} con avviso di movimento${d.problems.length ? ` · ${C.esc(d.problems.join("; "))}` : ""}${tools.length ? `<div class="cam-warn">${C.esc(tools.join(" · "))}</div>` : ""}`;
  }

  function card(s) {
    const o = s.options;
    return `<div class="cam-card ${o.hidden ? "dim" : ""}" data-id="${C.esc(s.id)}">
      <div class="cam-shot" data-act="view"><img alt="${C.esc(s.name)}" style="${C.transform(s)}" draggable="false"><div class="cam-off" hidden>Nessuna immagine</div>
        ${s.record.recording ? '<span class="cam-rec">● REC</span>' : ""}</div>
      <div class="cam-body"><div class="cam-name">${o.favorite ? "★ " : ""}${C.esc(s.name)}</div>
        <div class="cam-meta">${C.badge(C.kind(s))}${s.main ? C.badge("in uso dalla visione", "ok") : ""}${o.room ? C.badge(o.room) : ""}${o.motion ? C.badge("movimento", "warn") : ""}${o.hidden ? C.badge("nascosta") : ""}</div>
        <div class="cam-actions"><button class="btn sm" data-act="view">Ingrandisci</button><button class="btn sm" data-act="photo">📷 Foto</button><button class="btn sm primary" data-act="detail">Opzioni</button></div></div></div>`;
  }

  function renderLive() {
    const rows = C.data.sources;
    $("cam-pane-live").innerHTML = rows.length ? `<div class="cam-grid">${rows.map(card).join("")}</div>`
      : '<div class="panel"><div class="faint">Nessuna sorgente. Collega una webcam (viene riconosciuta da sola) oppure usa «Aggiungi» per una telecamera di rete.</div></div>';
    refreshShots();
  }

  C.renderLive = () => renderLive();

  function refreshShots() {
    document.querySelectorAll("#cam-pane-live .cam-card").forEach((el, i) => {
      const img = el.querySelector("img"), off = el.querySelector(".cam-off");
      img.onload = () => { off.hidden = true; };
      img.onerror = () => { off.hidden = false; };
      setTimeout(() => { if (img.isConnected) img.src = `/api/cameras/live/${encodeURIComponent(el.dataset.id)}.jpg?t=${Date.now()}`; }, i * 250);
    });
  }

  C.lightbox = (id) => {
    const s = C.source(id), box = $("cam-lightbox");
    if (!s) return;
    const img = document.createElement("img");
    img.style.cssText = C.transform(s);
    img.alt = s.name;
    clearInterval(C.timers.box);
    if (s.stream) img.src = `/api/cameras/live/${encodeURIComponent(id)}.mjpg?t=${Date.now()}`;
    else { const tick = () => { img.src = `/api/cameras/live/${encodeURIComponent(id)}.jpg?t=${Date.now()}`; }; tick(); C.timers.box = setInterval(tick, 1000); }
    box.replaceChildren(img);
    box.hidden = false;
  };

  function closeBox() {
    clearInterval(C.timers.box);
    const box = $("cam-lightbox");
    box.hidden = true;
    box.replaceChildren();
  }

  C.photo = async (id) => {
    try { const p = await A.api("POST", `/api/cameras/source/${encodeURIComponent(id)}/photo`); A.toast(`Foto salvata (${C.bytes(p.size)})`); await C.reload(); if (C.pane === "live") renderLive(); }
    catch (e) { A.toast(e.message, true); }
  };

  C.show = async (pane) => {
    C.pane = pane;
    document.querySelectorAll("#cam-tabs [data-pane]").forEach((b) => b.classList.toggle("primary", b.dataset.pane === pane));
    document.querySelectorAll("#tab-cameras .cam-pane").forEach((el) => { el.hidden = el.id !== `cam-pane-${pane}`; });
    Object.entries(C.panes).forEach(([k, p]) => { if (k !== pane && k !== "detail" && p.leave) p.leave(); });
    if (!(await C.reload())) return;
    if (pane === "live") renderLive();
    else if (C.panes[pane]) C.panes[pane].load();
  };

  function init() {
    $("cam-tabs").addEventListener("click", (e) => { const b = e.target.closest("[data-pane]"); if (b) C.show(b.dataset.pane); });
    $("cam-pane-live").addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]"), card = e.target.closest(".cam-card");
      if (!act || !card) return;
      if (act.dataset.act === "view") C.lightbox(card.dataset.id);
      else if (act.dataset.act === "photo") C.photo(card.dataset.id);
      else if (act.dataset.act === "detail") C.panes.detail.open(card.dataset.id);
    });
    $("cam-lightbox").addEventListener("click", closeBox);
    Object.values(C.panes).forEach((p) => { if (p.init) p.init(); });
  }

  function load() {
    C.show(C.pane);
    clearInterval(C.timers.live);
    C.timers.live = setInterval(() => { if (A.isOn("cameras") && C.pane === "live" && $("cam-lightbox").hidden) refreshShots(); }, 3000);
  }

  function leave() {
    Object.values(C.timers).forEach(clearInterval);
    closeBox();
    Object.values(C.panes).forEach((p) => { if (p.leave) p.leave(); });
  }

  A.tab("cameras", { title: "Telecamere", init, load, leave });
})();
