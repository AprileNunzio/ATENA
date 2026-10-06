(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const mu = A.mu, esc = mu.esc;
  const main = () => mu.main();
  const PAGE = 60;

  const greeting = () => {
    const h = new Date().getHours();
    return h < 6 ? "Buonanotte" : h < 13 ? "Buongiorno" : h < 18 ? "Buon pomeriggio" : "Buonasera";
  };

  const rail = (cards) => `<div class="mu-rail">${cards}</div>`;
  const mixCard = (m) => `<div class="mu-card" data-act="mix" data-id="${esc(m.id)}">${mu.art(m.cover_key, !!m.cover_key)}
    <button class="go" data-act="play-mix" data-id="${esc(m.id)}" title="Riproduci">▶</button>
    <div class="t">${esc(m.title)}</div><div class="s">${esc(m.subtitle)}</div></div>`;
  const trackCard = (t, i, name) => `<div class="mu-card" data-act="play" data-list="${name}" data-i="${i}">${mu.art(t.album_key, !!t.cover)}
    <div class="t">${esc(t.title)}</div><div class="s">${esc(t.artist)}</div></div>`;

  function empty(stats) {
    return `<div class="panel"><b>La libreria è ancora vuota.</b>
      <p class="mu-note">Copia i brani nella cartella condivisa <code>06 Musica/Da smistare</code> (anche dalla rete) oppure trascinali nella sezione «Gestione»:
      Atena li legge, li ordina in <code>Libreria/Artista/Album</code> e li mostra qui. Brani trovati finora: ${stats.tracks || 0}.</p>
      <button class="btn primary" data-go="manage">Apri la gestione</button></div>`;
  }

  mu.views.home = async () => {
    const h = await mu.get("/api/music/home");
    if (!h.stats.tracks) { main().innerHTML = `<h2>${greeting()}</h2>${empty(h.stats)}`; bindGo(); return; }
    mu.sets.homeRecent = h.recent;
    mu.sets.homePopular = h.popular;
    main().innerHTML = `<h2>${greeting()}</h2>
      ${h.recent.length ? `<h3>Riprendi da dove eri rimasto</h3>${rail(h.recent.map((t, i) => trackCard(t, i, "homeRecent")).join(""))}` : ""}
      ${h.mixes.length ? `<h3>Mix per te</h3>${rail(h.mixes.map(mixCard).join(""))}` : ""}
      ${h.added.length ? `<h3>Aggiunti di recente</h3>${rail(h.added.map(mu.albumCard).join(""))}` : ""}
      ${h.popular.length ? `<h3>I più ascoltati</h3>${rail(h.popular.map((t, i) => trackCard(t, i, "homePopular")).join(""))}` : ""}
      <h3>Da riscoprire</h3>${rail(h.random.map(mu.albumCard).join(""))}
      <p class="mu-note">${h.stats.tracks} brani · ${h.stats.albums} album · ${h.stats.artists} artisti · ${mu.long(h.stats.seconds)} di musica</p>`;
  };

  function bindGo() {
    main().querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => mu.go(b.dataset.go)));
  }

  mu.views.search = async () => {
    main().innerHTML = `<h2>Cerca</h2><div class="mu-search"><input id="mu-q" placeholder="Brani, album, artisti…" autocomplete="off"></div><div id="mu-results"></div>`;
    const input = $("mu-q");
    let timer = null;
    const run = async () => {
      const q = input.value.trim();
      mu.searchText = q;
      if (!q) { $("mu-results").innerHTML = '<div class="mu-empty">Scrivi qualcosa: la ricerca è istantanea.</div>'; return; }
      try {
        const r = await mu.get(`/api/music/search?q=${encodeURIComponent(q)}`);
        if (q !== input.value.trim()) return;
        $("mu-results").innerHTML = (r.artists.length ? `<h3>Artisti</h3><div class="mu-grid">${r.artists.map((a) => mu.artistCard({ ...a, album_key: "", cover: 0 })).join("")}</div>` : "")
          + (r.albums.length ? `<h3>Album</h3><div class="mu-grid">${r.albums.map(mu.albumCard).join("")}</div>` : "")
          + `<h3>Brani</h3>${mu.table("search", r.tracks, { empty: "Nessun brano trovato." })}`;
      } catch (e) { $("mu-results").textContent = e.message; }
    };
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 220); });
    input.value = mu.searchText || "";
    input.focus();
    run();
  };

  mu.views.tracks = async (arg) => {
    const genre = (arg && arg.genre) || "";
    const state = { sort: (arg && arg.sort) || "title", offset: 0, all: [], total: 0 };
    main().innerHTML = `<h2>${genre ? esc(genre) : "Tutti i brani"}</h2>
      <div class="mu-toolbar"><select id="mu-sort"><option value="title">Titolo</option><option value="artist">Artista</option><option value="album">Album</option>
        <option value="recent">Aggiunti di recente</option><option value="plays">Più ascoltati</option><option value="year">Anno</option><option value="duration">Durata</option><option value="random">Casuale</option></select>
        <button class="btn sm" id="mu-all-play">▶ Riproduci</button><button class="btn sm" id="mu-all-shuffle">⤮ Casuale</button><span class="mu-note" id="mu-count"></span></div>
      <div id="mu-list"></div><div class="mu-actions"><button class="btn" id="mu-more" hidden>Carica altri</button></div>`;
    $("mu-sort").value = state.sort;
    const load = async (reset) => {
      if (reset) { state.offset = 0; state.all = []; }
      const r = await mu.get(`/api/music/tracks?sort=${state.sort}&limit=${PAGE}&offset=${state.offset}${genre ? `&genre=${encodeURIComponent(genre)}` : ""}`);
      state.all = state.all.concat(r.tracks);
      state.total = r.total;
      state.offset += r.tracks.length;
      $("mu-list").innerHTML = mu.table("tracks", state.all);
      $("mu-count").textContent = genre ? `${state.all.length} brani` : `${state.all.length} di ${r.total}`;
      $("mu-more").hidden = r.tracks.length < PAGE;
    };
    $("mu-sort").addEventListener("change", (e) => { state.sort = e.target.value; load(true).catch(mu.err); });
    $("mu-more").addEventListener("click", () => load(false).catch(mu.err));
    $("mu-all-play").addEventListener("click", () => mu.play(mu.sets.tracks || [], 0));
    $("mu-all-shuffle").addEventListener("click", () => mu.play(mu.sets.tracks || [], 0, { shuffle: true }));
    await load(true);
  };

  mu.views.favorites = async () => {
    const r = await mu.get("/api/music/tracks?liked=true&limit=500&sort=recent");
    main().innerHTML = `<h2>Preferiti</h2><div class="mu-actions"><button class="btn primary" id="mu-play">▶ Riproduci</button><button class="btn" id="mu-shuf">⤮ Casuale</button></div>${mu.table("favorites", r.tracks, { empty: "Tocca il cuore accanto a un brano per trovarlo qui." })}`;
    $("mu-play").addEventListener("click", () => mu.play(r.tracks, 0));
    $("mu-shuf").addEventListener("click", () => mu.play(r.tracks, 0, { shuffle: true }));
  };

  mu.views.history = async () => {
    const r = await mu.get("/api/music/history?limit=100");
    main().innerHTML = `<h2>Ascoltati di recente</h2>${mu.table("history", r.tracks, { empty: "Ancora nessun ascolto." })}`;
  };

  mu.views.albums = async () => {
    const state = { sort: "title", offset: 0, all: [] };
    main().innerHTML = `<h2>Album</h2><div class="mu-toolbar"><select id="mu-sort"><option value="title">Titolo</option><option value="artist">Artista</option><option value="recent">Aggiunti di recente</option>
      <option value="year">Anno</option><option value="plays">Più ascoltati</option><option value="random">Casuale</option></select></div><div class="mu-grid" id="mu-grid"></div>
      <div class="mu-actions"><button class="btn" id="mu-more" hidden>Carica altri</button></div>`;
    const load = async (reset) => {
      if (reset) { state.offset = 0; state.all = []; }
      const r = await mu.get(`/api/music/albums?sort=${state.sort}&limit=${PAGE}&offset=${state.offset}`);
      state.all = state.all.concat(r.albums);
      state.offset += r.albums.length;
      $("mu-grid").innerHTML = state.all.map(mu.albumCard).join("") || '<div class="mu-empty">Nessun album.</div>';
      $("mu-more").hidden = r.albums.length < PAGE;
    };
    $("mu-sort").addEventListener("change", (e) => { state.sort = e.target.value; load(true).catch(mu.err); });
    $("mu-more").addEventListener("click", () => load(false).catch(mu.err));
    await load(true);
  };

  mu.views.album = async (key) => {
    const a = await mu.get(`/api/music/albums/${encodeURIComponent(key)}`);
    mu.sets.album = a.tracks;
    main().innerHTML = `${mu.backButton()}<div class="mu-head">${a.cover ? `<img src="${mu.cover(a.album_key, 600)}" alt="">` : '<div class="mu-cover-lg">♪</div>'}
      <div class="meta"><div class="kind">Album</div><h1>${esc(a.album)}</h1>
        <div><a data-act="artist" data-key="${esc(a.tracks[0].artist_key)}" style="cursor:pointer;color:var(--cyan)">${esc(a.album_artist)}</a>${a.year ? ` · ${a.year}` : ""} · ${a.tracks.length} brani · ${mu.long(a.duration)}</div>
        <div class="mu-actions"><button class="btn primary" id="mu-play">▶ Riproduci</button><button class="btn" id="mu-shuf">⤮ Casuale</button><button class="btn" id="mu-queue">＋ In coda</button>
          <button class="btn" id="mu-share">⇪ Condividi</button><button class="btn" id="mu-edit">✎ Modifica</button></div></div></div>
      ${mu.table("album", a.tracks, { album: false, n: null })}`;
    $("mu-play").addEventListener("click", () => mu.play(a.tracks, 0));
    $("mu-shuf").addEventListener("click", () => mu.play(a.tracks, 0, { shuffle: true }));
    $("mu-queue").addEventListener("click", () => mu.enqueue(a.tracks));
    $("mu-share").addEventListener("click", () => mu.share && mu.share("album", a.album_key));
    $("mu-edit").addEventListener("click", () => mu.edit && mu.edit(a.tracks[0], "album"));
  };

  mu.views.artists = async () => {
    const r = await mu.get("/api/music/artists?limit=500");
    main().innerHTML = `<h2>Artisti</h2><div class="mu-grid">${r.artists.map((a) => mu.artistCard({ ...a, album_key: a.album_key || "" })).join("") || '<div class="mu-empty">Nessun artista.</div>'}</div>`;
  };

  mu.views.artist = async (key) => {
    const a = await mu.get(`/api/music/artists/${encodeURIComponent(key)}`);
    mu.sets.popular = a.popular;
    main().innerHTML = `${mu.backButton()}<div class="mu-head"><div class="meta"><div class="kind">Artista</div><h1>${esc(a.artist)}</h1>
      <div>${a.tracks} brani · ${a.albums.length} album · ${mu.long(a.duration)}</div>
      <div class="mu-actions"><button class="btn primary" id="mu-play">▶ Mix dell'artista</button><button class="btn" id="mu-radio">◎ Radio</button></div></div></div>
      <h3>Brani più ascoltati</h3>${mu.table("popular", a.popular)}
      <h3>Album</h3><div class="mu-grid">${a.albums.map(mu.albumCard).join("")}</div>`;
    $("mu-play").addEventListener("click", () => mu.act["play-mix"]({ id: `artist:${key}` }));
    $("mu-radio").addEventListener("click", () => a.popular[0] && mu.radioFrom(a.popular[0]));
  };

  mu.views.genres = async () => {
    const r = await mu.get("/api/music/genres");
    main().innerHTML = `<h2>Generi</h2><div class="mu-chips">${r.genres.map((g) => `<button data-act="genre" data-name="${esc(g.genre)}">${esc(g.genre)} <small>${g.tracks}</small></button>`).join("") || '<span class="mu-empty">Nessun genere nei tag dei brani.</span>'}</div>
      <h3>Decenni</h3><div class="mu-chips">${r.decades.map((d) => `<button data-act="mix" data-id="decade:${d.decade}">Anni ${d.decade} <small>${d.tracks}</small></button>`).join("")}</div>`;
  };

  mu.views.mix = async (id) => {
    const r = await mu.get(`/api/music/mix/${encodeURIComponent(id)}`);
    const names = { rediscover: "Riscoperta", unheard: "Mai ascoltati", liked: "I tuoi preferiti", recent: "Novità" };
    const [kind, value] = id.split(":");
    const title = names[id] || (kind === "decade" ? `Anni ${value}` : kind === "genre" ? `Mix ${value}` : kind === "artist" && r.tracks[0] ? `Mix ${r.tracks[0].artist}` : "Mix");
    main().innerHTML = `${mu.backButton()}<h2>${esc(title)}</h2><div class="mu-actions"><button class="btn primary" id="mu-play">▶ Riproduci</button>
      <button class="btn" id="mu-queue">＋ In coda</button><button class="btn" id="mu-save">💾 Salva come playlist</button><button class="btn" id="mu-again">⟳ Rigenera</button></div>${mu.table("mix", r.tracks, { empty: "Niente da mostrare per ora." })}`;
    $("mu-play").addEventListener("click", () => mu.play(r.tracks, 0));
    $("mu-queue").addEventListener("click", () => mu.enqueue(r.tracks));
    $("mu-again").addEventListener("click", () => mu.reload());
    $("mu-save").addEventListener("click", async () => {
      try { const p = await mu.post("/api/music/playlists", { name: title, tracks: r.tracks.map((t) => t.id) }); A.toast("Playlist creata"); mu.reloadPlaylists(); mu.go("playlist", p.id); } catch (e) { mu.err(e); }
    });
  };

  mu.views.stats = async () => {
    const days = (mu.view.arg && mu.view.arg.days) || 30;
    const s = await mu.get(`/api/music/stats?days=${days}`);
    const max = Math.max(1, ...s.hours.map((h) => h.n));
    const hours = Array.from({ length: 24 }, (_, h) => (s.hours.find((x) => x.hour === h) || { n: 0 }).n);
    mu.sets.statsTop = s.top;
    main().innerHTML = `<h2>Le tue statistiche</h2><div class="mu-chips">${[[7, "7 giorni"], [30, "30 giorni"], [365, "Un anno"]].map(([d, l]) => `<button class="${d === days ? "on" : ""}" data-days="${d}">${l}</button>`).join("")}</div>
      <div class="mu-stats"><div class="mu-stat"><b>${s.plays || 0}</b><span>ascolti</span></div><div class="mu-stat"><b>${mu.long(s.seconds || 0)}</b><span>di musica ascoltata</span></div>
        <div class="mu-stat"><b>${s.tracks || 0}</b><span>brani diversi</span></div></div>
      <h3>Artisti più ascoltati</h3>${s.artists.map((a, i) => `<div class="mu-q"><span class="n">${i + 1}</span><div class="tt"><b>${esc(a.artist)}</b><small>${a.n} ascolti</small></div></div>`).join("") || '<div class="mu-empty">Ancora nessun dato.</div>'}
      <h3>Generi</h3><div class="mu-chips">${s.genres.map((g) => `<button>${esc(g.genre)} <small>${g.n}</small></button>`).join("")}</div>
      <h3>A che ora ascolti</h3><div class="mu-bars">${hours.map((n, h) => `<i title="${h}:00 — ${n}" style="height:${Math.round((n / max) * 100)}%"></i>`).join("")}</div>
      <h3>I tuoi brani del periodo</h3>${mu.table("statsTop", s.top, { empty: "Ascolta qualcosa e torna qui." })}`;
    main().querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => mu.go("stats", { days: Number(b.dataset.days) }, true)));
  };
})();
