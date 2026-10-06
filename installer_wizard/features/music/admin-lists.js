(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const mu = A.mu, esc = mu.esc;
  const L = mu.pl = {};
  let playlists = [];
  mu.plctx = null;

  mu.modal = (title, html, onOk, okLabel = "Salva") => {
    const wrap = document.createElement("div");
    wrap.className = "mu-modal";
    wrap.innerHTML = `<div class="mu-dialog"><h3>${esc(title)}</h3><div class="mu-dialog-body">${html}</div>
      <div class="mu-actions" style="justify-content:flex-end"><button class="btn" data-m="cancel">Annulla</button>${onOk ? `<button class="btn primary" data-m="ok">${esc(okLabel)}</button>` : ""}</div></div>`;
    document.body.appendChild(wrap);
    const close = () => wrap.remove();
    wrap.addEventListener("click", async (e) => {
      if (e.target === wrap || e.target.dataset.m === "cancel") close();
      else if (e.target.dataset.m === "ok") { try { if ((await onOk(wrap)) !== false) close(); } catch (err) { mu.err(err); } }
    });
    const first = wrap.querySelector("input, select");
    if (first) first.focus();
    return wrap;
  };

  L.reload = async () => {
    try { playlists = (await mu.get("/api/music/playlists")).playlists; } catch (err) { playlists = []; }
    $("mu-playlists").innerHTML = playlists.map((p) => `<button class="pl" data-act="playlist" data-id="${p.id}"><span>${p.kind === "smart" ? "✦ " : ""}${esc(p.name)}</span><small>${p.tracks}</small></button>`).join("")
      || '<div class="mu-note" style="padding:4px 10px">Nessuna playlist.</div>';
  };
  mu.reloadPlaylists = L.reload;

  const FIELDS = [["genre", "Genere (esatto)", "text"], ["year_from", "Anno da", "number"], ["year_to", "Anno a", "number"], ["recent_days", "Aggiunti negli ultimi (giorni)", "number"],
    ["forgotten_days", "Non ascoltati da (giorni)", "number"], ["limit", "Numero massimo di brani", "number"]];

  function ruleForm(rule = {}) {
    return `<div class="mu-form">${FIELDS.map(([k, l, t]) => `<label>${l}<input data-rule="${k}" type="${t}" value="${esc(rule[k] || "")}"></label>`).join("")}
      <label>Ordine<select data-rule="sort">${[["recent", "Più recenti"], ["plays", "Più ascoltati"], ["random", "Casuale"], ["title", "Titolo"], ["year", "Anno"], ["played", "Ascoltati da poco"]]
        .map(([v, l]) => `<option value="${v}" ${rule.sort === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      ${[["never_played", "Mai ascoltati"], ["played", "Già ascoltati"], ["liked", "Solo preferiti"]].map(([k, l]) => `<label class="switch"><input type="checkbox" data-rule="${k}" ${rule[k] ? "checked" : ""}> ${l}</label>`).join("")}</div>`;
  }

  function readRule(root) {
    const rule = {};
    root.querySelectorAll("[data-rule]").forEach((el) => {
      const v = el.type === "checkbox" ? el.checked : el.value.trim();
      if (v !== "" && v !== false) rule[el.dataset.rule] = el.type === "number" ? Number(v) : v;
    });
    return rule;
  }

  L.create = async () => {
    const name = prompt("Nome della nuova playlist");
    if (!name || !name.trim()) return;
    try { const r = await mu.post("/api/music/playlists", { name: name.trim() }); await L.reload(); mu.go("playlist", r.id); } catch (e) { mu.err(e); }
  };

  L.createSmart = () => {
    mu.modal("Nuova playlist intelligente", `<label>Nome<input id="mu-pl-name" placeholder="Per esempio: Rock anni 80"></label>${ruleForm({ sort: "random", limit: 50 })}
      <p class="mu-note">Si aggiorna da sola: ogni volta che la apri trova i brani che rispettano queste regole.</p>`, async (wrap) => {
      const name = wrap.querySelector("#mu-pl-name").value.trim();
      if (!name) { A.toast("Serve un nome", true); return false; }
      const r = await mu.post("/api/music/playlists", { name, kind: "smart", rule: readRule(wrap) });
      await L.reload();
      mu.go("playlist", r.id);
      return true;
    }, "Crea");
  };

  mu.views.playlist = async (id) => {
    const p = await mu.get(`/api/music/playlists/${id}`);
    mu.plctx = { id: p.id, mine: p.mine, kind: p.kind };
    mu.sets.playlist = p.tracks;
    $("mu-main").innerHTML = `${mu.backButton()}<div class="mu-head"><div class="mu-cover-lg">${p.kind === "smart" ? "✦" : "♫"}</div><div class="meta"><div class="kind">${p.kind === "smart" ? "Playlist intelligente" : "Playlist"}${p.shared ? " · condivisa" : ""}</div>
      <h1>${esc(p.name)}</h1><div>${esc(p.owner)} · ${p.tracks.length} brani · ${mu.long(p.seconds)}</div>${p.description ? `<div class="mu-note">${esc(p.description)}</div>` : ""}
      <div class="mu-actions"><button class="btn primary" id="pl-play">▶ Riproduci</button><button class="btn" id="pl-shuf">⤮ Casuale</button><button class="btn" id="pl-queue">＋ In coda</button>
        <button class="btn" id="pl-menu">⋯ Altro</button></div></div></div>${mu.table("playlist", p.tracks, { empty: p.kind === "smart" ? "Nessun brano rispetta queste regole." : "Playlist vuota: usa «⋯» su un brano per aggiungerlo." })}`;
    $("pl-play").addEventListener("click", () => mu.play(p.tracks, 0));
    $("pl-shuf").addEventListener("click", () => mu.play(p.tracks, 0, { shuffle: true }));
    $("pl-queue").addEventListener("click", () => mu.enqueue(p.tracks));
    $("pl-menu").addEventListener("click", (e) => mu.menu(e.currentTarget, [
      ...(p.mine ? [{ label: "Rinomina", fn: () => rename(p) }, { label: p.shared ? "Rendi privata" : "Condividi con gli altri utenti", fn: () => toggleShared(p) }] : []),
      ...(p.mine && p.kind === "smart" ? [{ label: "Modifica le regole", fn: () => editRule(p) }] : []),
      { label: "Crea un link condiviso", fn: () => mu.share("playlist", String(p.id)) },
      { label: "Esporta M3U nella cartella Playlist", fn: () => exportM3u(p) },
      { label: "Scarica M3U", fn: () => { window.location.href = `/api/music/playlists/${p.id}/m3u`; } },
      ...(p.mine ? ["-", { label: "Elimina la playlist", fn: () => remove(p) }] : [])]));
  };

  async function rename(p) {
    const name = prompt("Nuovo nome", p.name);
    if (!name || !name.trim()) return;
    try { await mu.post(`/api/music/playlists/${p.id}`, { name: name.trim() }); await L.reload(); mu.reload(); } catch (e) { mu.err(e); }
  }

  async function toggleShared(p) {
    try { await mu.post(`/api/music/playlists/${p.id}`, { name: p.name, shared: !p.shared }); await L.reload(); mu.reload(); } catch (e) { mu.err(e); }
  }

  function editRule(p) {
    mu.modal("Regole della playlist", ruleForm(JSON.parse(p.rule || "{}")), async (wrap) => {
      await mu.post(`/api/music/playlists/${p.id}`, { name: p.name, rule: readRule(wrap) });
      mu.reload();
    });
  }

  async function exportM3u(p) {
    try { const r = await mu.post(`/api/music/playlists/${p.id}/export`); A.toast(`Salvata in Playlist/${r.file}`); } catch (e) { mu.err(e); }
  }

  async function remove(p) {
    if (!confirm(`Eliminare la playlist «${p.name}»? I brani restano nella libreria.`)) return;
    try { await mu.post(`/api/music/playlists/${p.id}/delete`); await L.reload(); mu.go("home", null, true); } catch (e) { mu.err(e); }
  }

  async function addTo(track, id) {
    try { await mu.post(`/api/music/playlists/${id}/add`, { tracks: [track.id] }); A.toast("Aggiunto alla playlist"); L.reload(); } catch (e) { mu.err(e); }
  }

  function pickPlaylist(anchor, track) {
    const mine = playlists.filter((p) => p.mine && p.kind === "manual");
    mu.menu(anchor, [...mine.map((p) => ({ label: p.name, fn: () => addTo(track, p.id) })),
      { label: "＋ Nuova playlist…", fn: async () => {
        const name = prompt("Nome della nuova playlist");
        if (!name || !name.trim()) return;
        try { await mu.post("/api/music/playlists", { name: name.trim(), tracks: [track.id] }); await L.reload(); A.toast("Playlist creata"); } catch (e) { mu.err(e); }
      } }], "Aggiungi a…");
  }

  mu.trackMenu = (anchor, t, listName, i) => {
    const inPlaylist = listName === "playlist" && mu.plctx && mu.plctx.mine && mu.plctx.kind === "manual";
    mu.menu(anchor, [
      { label: "Riproduci", fn: () => mu.play(mu.sets[listName] || [t], mu.sets[listName] ? i : 0) },
      { label: "Riproduci subito dopo", fn: () => mu.enqueue([t], true) },
      { label: "Aggiungi alla coda", fn: () => mu.enqueue([t]) },
      { label: "Aggiungi a una playlist…", fn: () => setTimeout(() => pickPlaylist(anchor, t), 0) },
      ...(inPlaylist ? [{ label: "Rimuovi da questa playlist", fn: async () => { try { await mu.post(`/api/music/playlists/${mu.plctx.id}/remove`, { positions: [i] }); mu.reload(); L.reload(); } catch (e) { mu.err(e); } } },
        ...(i > 0 ? [{ label: "Sposta su", fn: async () => { try { await mu.post(`/api/music/playlists/${mu.plctx.id}/move`, { from: i, to: i - 1 }); mu.reload(); } catch (e) { mu.err(e); } } }] : []),
        { label: "Sposta giù", fn: async () => { try { await mu.post(`/api/music/playlists/${mu.plctx.id}/move`, { from: i, to: i + 1 }); mu.reload(); } catch (e) { mu.err(e); } } }] : []),
      "-",
      { label: "Radio da questo brano", fn: () => mu.radioFrom(t) },
      { label: "Vai all'album", fn: () => mu.go("album", t.album_key) },
      { label: "Vai all'artista", fn: () => mu.go("artist", t.artist_key) },
      "-",
      { label: `Valuta${t.stars ? ` (${"★".repeat(t.stars)})` : ""}…`, fn: () => setTimeout(() => rate(anchor, t), 0) },
      { label: "Crea un link condiviso", fn: () => mu.share("track", String(t.id)) },
      { label: "Modifica i dati…", fn: () => mu.edit(t, "track") },
      { label: "Sposta nel cestino", fn: () => trash(t) }]);
  };

  function rate(anchor, t) {
    mu.menu(anchor, [0, 1, 2, 3, 4, 5].map((n) => ({ label: n ? "★".repeat(n) + "☆".repeat(5 - n) : "Nessuna valutazione", fn: async () => {
      try { await mu.post(`/api/music/tracks/${t.id}/rate`, { stars: n }); t.stars = n; A.toast("Valutazione salvata"); } catch (e) { mu.err(e); }
    } })), "Valutazione");
  }

  async function trash(t) {
    if (!confirm(`Spostare «${t.title}» nel cestino della libreria?`)) return;
    try { await mu.post(`/api/music/tracks/${t.id}/trash`); A.toast("Spostato nel cestino"); mu.reload(); } catch (e) { mu.err(e); }
  }

  mu.edit = (t, scope) => {
    const album = scope === "album";
    mu.modal(album ? "Modifica l'album" : "Modifica il brano", `<div class="mu-form">
      ${album ? "" : `<label>Titolo<input data-f="title" value="${esc(t.title)}"></label><label>Artista<input data-f="artist" value="${esc(t.artist)}"></label><label>Numero traccia<input data-f="track_no" type="number" value="${t.track_no || ""}"></label>`}
      <label>Album<input data-f="album" value="${esc(t.album)}"></label><label>Artista dell'album<input data-f="album_artist" value="${esc(t.album_artist)}"></label>
      <label>Genere<input data-f="genre" value="${esc(t.genre)}"></label><label>Anno<input data-f="year" type="number" value="${t.year || ""}"></label>
      ${album ? "" : `<label>Applica a<select data-f="scope"><option value="track">Solo questo brano</option><option value="album">Tutto l'album (album, artista album, genere, anno)</option></select></label>`}</div>
      <p class="mu-note">Le modifiche valgono per la libreria di Atena; i file restano com'erano.</p>`, async (wrap) => {
      const body = { scope: album ? "album" : "track" };
      wrap.querySelectorAll("[data-f]").forEach((el) => { if (el.value.trim() !== "") body[el.dataset.f] = el.dataset.f.match(/year|track_no/) ? Number(el.value) : el.value.trim(); });
      const r = await mu.post(`/api/music/tracks/${t.id}/edit`, body);
      A.toast(`Modificati ${r.changed} brani`);
      mu.reload();
    });
  };

  mu.share = (kind, ref) => {
    mu.modal("Crea un link condiviso", `<div class="mu-form"><label>Il link vale<select id="mu-share-h"><option value="1">1 ora</option><option value="24" selected>1 giorno</option>
      <option value="168">1 settimana</option><option value="720">30 giorni</option></select></label></div>
      <p class="mu-note">Chi ha il link può ascoltare solo questo contenuto, senza accedere ad Atena, finché non scade. Puoi revocarlo dalla sezione «Gestione e condivisione».</p>`, async (wrap) => {
      const r = await mu.post("/api/music/shares", { kind, ref, hours: Number(wrap.querySelector("#mu-share-h").value) });
      mu.modal("Link pronto", `<div class="mu-form"><input id="mu-share-url" readonly value="${esc(r.url)}"></div><p class="mu-note">Funziona solo nella tua rete, a meno che tu non la renda raggiungibile da fuori.</p>`, null);
      const input = document.getElementById("mu-share-url");
      input.addEventListener("focus", () => input.select());
      A.copy(r.url, "link condiviso");
    }, "Crea e copia");
  };

  L.init = () => {
    $("mu-new-playlist").addEventListener("click", (e) => mu.menu(e.currentTarget, [
      { label: "Playlist vuota…", fn: () => L.create() }, { label: "Playlist intelligente…", fn: () => L.createSmart() }]));
    L.reload();
  };
})();
