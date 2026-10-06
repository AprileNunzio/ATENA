(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const mu = A.mu, esc = mu.esc;
  const Z = mu.queue = {};
  let pane = "queue", shown = false, lyrics = { id: null, lines: [], plain: "", on: -1 };

  const body = () => $("mu-drawer-body");

  function queueItem(t, i, now) {
    return `<div class="mu-q ${i === now ? "now" : ""}" data-i="${i}"><div class="tt" data-q="jump"><b>${esc(t.title)}</b><small>${esc(t.artist)} · ${mu.time(t.duration)}</small></div>
      ${i === now ? "" : `<button data-q="up" title="Su">▲</button><button data-q="down" title="Giù">▼</button><button data-q="del" title="Rimuovi">✕</button>`}</div>`;
  }

  function paintQueue() {
    const { tracks, index } = mu.player.queue();
    if (!tracks.length) { body().innerHTML = '<div class="mu-empty">La coda è vuota: scegli qualcosa da ascoltare.</div>'; return; }
    const upcoming = tracks.slice(index + 1);
    const seconds = upcoming.reduce((n, t) => n + (t.duration || 0), 0);
    body().innerHTML = `<div class="mu-actions"><button class="btn sm" data-q="clear">Svuota</button><button class="btn sm" data-q="save">Salva come playlist</button></div>
      <div class="mu-note">In riproduzione</div>${index >= 0 ? queueItem(tracks[index], index, index) : ""}
      <div class="mu-note">Prossimi: ${upcoming.length} brani · ${mu.long(seconds)}</div>${upcoming.slice(0, 120).map((t, k) => queueItem(t, index + 1 + k, index)).join("")}`;
  }

  async function queueClick(e) {
    const el = e.target.closest("[data-q]");
    if (!el) return;
    const row = el.closest(".mu-q");
    const i = row ? Number(row.dataset.i) : -1;
    const P = mu.player;
    if (el.dataset.q === "jump") P.jump(i);
    else if (el.dataset.q === "del") P.removeAt(i);
    else if (el.dataset.q === "up") P.moveInQueue(i, i - 1);
    else if (el.dataset.q === "down") P.moveInQueue(i, i + 1);
    else if (el.dataset.q === "clear") P.clear();
    else if (el.dataset.q === "save") {
      const { tracks } = P.queue();
      const name = prompt("Nome della nuova playlist", "La mia coda");
      if (!name) return;
      try { await mu.post("/api/music/playlists", { name, tracks: tracks.map((t) => t.id) }); A.toast("Playlist creata"); mu.reloadPlaylists(); } catch (err) { mu.err(err); }
    }
  }

  Z.loadLyrics = async () => {
    const t = mu.current;
    if (!t || lyrics.id === t.id) return;
    lyrics = { id: t.id, lines: [], plain: "", on: -1, loading: true };
    if (pane === "lyrics") paintLyrics();
    try {
      const r = await mu.get(`/api/music/lyrics/${t.id}`);
      if (lyrics.id !== t.id) return;
      lyrics = { id: t.id, lines: r.synced || [], plain: r.plain || "", on: -1, loading: false };
    } catch (err) { lyrics = { id: t.id, lines: [], plain: "", on: -1, loading: false }; }
    if (pane === "lyrics") paintLyrics();
  };

  function paintLyrics() {
    const t = mu.current;
    if (!t) { body().innerHTML = '<div class="mu-empty">Nessun brano in riproduzione.</div>'; return; }
    if (lyrics.loading) { body().innerHTML = '<div class="mu-empty">Cerco il testo…</div>'; return; }
    if (lyrics.lines.length) body().innerHTML = `<div class="mu-lyrics">${lyrics.lines.map((l, i) => `<p data-t="${l.t}" data-n="${i}">${esc(l.text) || "♪"}</p>`).join("")}</div>`;
    else if (lyrics.plain) body().innerHTML = `<div class="mu-lyrics" style="text-align:left;white-space:pre-wrap;line-height:1.6">${esc(lyrics.plain)}</div>`;
    else body().innerHTML = `<div class="mu-empty">Testo non disponibile per «${esc(t.title)}». Puoi metterlo in un file <code>.lrc</code> accanto al brano.</div>`;
  }

  Z.tick = (position) => {
    if (!shown || pane !== "lyrics" || !lyrics.lines.length) return;
    let on = -1;
    for (let i = 0; i < lyrics.lines.length; i++) { if (lyrics.lines[i].t <= position + 0.15) on = i; else break; }
    if (on === lyrics.on) return;
    lyrics.on = on;
    body().querySelectorAll(".mu-lyrics p").forEach((p, i) => p.classList.toggle("on", i === on));
    const el = body().querySelector(".mu-lyrics p.on");
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  function paintEq() {
    const P = mu.player, st = P.eq.state(), s = P.state();
    body().innerHTML = `<div class="mu-form"><label>Profilo<select id="mu-preset">${Object.keys(P.eq.presets).concat(st.preset === "Personalizzato" ? ["Personalizzato"] : [])
      .map((n) => `<option ${n === st.preset ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>
      <div class="mu-eq">${P.eq.bands.map((f, i) => `<label><span>${st.gains[i] > 0 ? "+" : ""}${st.gains[i]}</span><input type="range" min="-12" max="12" step="1" value="${st.gains[i]}" data-band="${i}"><span>${f >= 1000 ? f / 1000 + "k" : f}</span></label>`).join("")}</div>
      <label class="switch"><input type="checkbox" id="mu-norm" ${st.normalize ? "checked" : ""}> Livella il volume tra i brani</label>
      <div class="mu-form" style="margin-top:12px"><label>Dissolvenza tra i brani<select id="mu-xf">${[0, 3, 6, 10].map((v) => `<option value="${v}" ${v === Number(s.crossfade) ? "selected" : ""}>${v ? `${v} secondi` : "Nessuna"}</option>`).join("")}</select></label></div>
      <p class="mu-note">Le impostazioni valgono per la riproduzione in questo browser.</p>`;
  }

  function eqEvents(e) {
    const P = mu.player;
    if (e.target.id === "mu-preset") { P.eq.preset(e.target.value); paintEq(); }
    else if (e.target.id === "mu-norm") P.eq.normalize(e.target.checked);
    else if (e.target.id === "mu-xf") P.crossfade(e.target.value);
    else if (e.target.dataset.band !== undefined) {
      P.eq.set(Number(e.target.dataset.band), Number(e.target.value));
      e.target.parentNode.firstChild.textContent = `${Number(e.target.value) > 0 ? "+" : ""}${e.target.value}`;
      const select = $("mu-preset");
      if (select && ![...select.options].some((o) => o.value === "Personalizzato")) { select.add(new Option("Personalizzato", "Personalizzato")); select.value = "Personalizzato"; }
    }
  }

  Z.refresh = () => {
    if (!shown) return;
    if (pane === "queue") paintQueue(); else if (pane === "lyrics") { Z.loadLyrics(); paintLyrics(); } else paintEq();
  };

  function show(name) {
    pane = name;
    shown = true;
    $("mu-drawer").hidden = false;
    document.querySelector(".mu-app").classList.add("drawer");
    $("mu-drawer-tabs").querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.pane === name));
    Z.refresh();
  }

  Z.open = (name) => {
    if (shown && pane === name) { shown = false; $("mu-drawer").hidden = true; document.querySelector(".mu-app").classList.remove("drawer"); return; }
    show(name);
  };

  Z.init = () => {
    $("mu-drawer-tabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-pane]"); if (b) show(b.dataset.pane); });
    $("mu-drawer-body").addEventListener("click", queueClick);
    $("mu-drawer-body").addEventListener("input", eqEvents);
    $("mu-drawer-body").addEventListener("change", eqEvents);
    $("mu-drawer-body").addEventListener("click", (e) => {
      const p = e.target.closest(".mu-lyrics p[data-t]");
      if (p) mu.player.seekTo(Number(p.dataset.t));
    });
  };
})();
