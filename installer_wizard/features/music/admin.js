(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const mu = A.mu = { view: { name: "home", arg: null }, stack: [], views: {}, sets: {}, cfg: {}, ready: false, user: "", out: { id: "browser", remote: false, name: "Questo browser" } };

  mu.esc = (s) => fmt.esc(s == null ? "" : s);
  mu.time = (s) => {
    s = Math.max(0, Math.round(Number(s) || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
  };
  mu.long = (s) => {
    const m = Math.round((Number(s) || 0) / 60);
    return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
  };
  mu.cover = (key, size = 300) => `/api/music/cover/${encodeURIComponent(key)}?size=${size}`;
  mu.get = (url) => A.api("GET", url);
  mu.post = (url, body) => A.api("POST", url, body || {});
  mu.main = () => $("mu-main");
  mu.err = (e) => A.toast(e.message || String(e), true);

  mu.art = (key, hasCover, cls = "") => (hasCover === false || !key
    ? `<div class="cv ${cls}">♪</div>` : `<div class="cv ${cls}"><img loading="lazy" src="${mu.cover(key, 300)}" alt="" onerror="this.remove()"></div>`);

  mu.albumCard = (a) => `<div class="mu-card" data-act="album" data-key="${mu.esc(a.album_key)}">${mu.art(a.album_key, a.cover)}
    <button class="go" data-act="play-album" data-key="${mu.esc(a.album_key)}" title="Riproduci">▶</button>
    <div class="t">${mu.esc(a.album)}</div><div class="s">${mu.esc([a.album_artist, a.year || ""].filter(Boolean).join(" · "))}</div></div>`;

  mu.artistCard = (a) => `<div class="mu-card round" data-act="artist" data-key="${mu.esc(a.artist_key)}">${mu.art(a.album_key || a.cover_key, a.cover, "round")}
    <div class="t">${mu.esc(a.artist)}</div><div class="s">${a.tracks} brani · ${a.albums} album</div></div>`;

  mu.row = (name, t, i, opts = {}) => `<tr class="row ${mu.current && mu.current.id === t.id ? "now" : ""}" data-list="${name}" data-i="${i}">
    <td class="n">${opts.number === false ? "" : (opts.n || i + 1)}</td>
    <td><div class="ti" data-act="play" data-list="${name}" data-i="${i}">${t.cover ? `<img loading="lazy" src="${mu.cover(t.album_key, 96)}" alt="" onerror="this.outerHTML='<span class=ph>♪</span>'">` : '<span class="ph">♪</span>'}
      <div><b>${mu.esc(t.title)}</b><small>${mu.esc(t.artist)}</small></div></div></td>
    ${opts.album === false ? "" : `<td class="dim"><a data-act="album" data-key="${mu.esc(t.album_key)}" style="cursor:pointer">${mu.esc(t.album)}</a></td>`}
    <td><button class="ic ${t.liked ? "on" : ""}" data-act="like" data-list="${name}" data-i="${i}" title="Preferito">${t.liked ? "♥" : "♡"}</button></td>
    <td class="d">${mu.time(t.duration)}</td>
    <td><button class="ic more" data-act="menu" data-list="${name}" data-i="${i}" title="Altro">⋯</button></td></tr>`;

  mu.table = (name, tracks, opts = {}) => {
    mu.sets[name] = tracks;
    if (!tracks.length) return `<div class="mu-empty">${opts.empty || "Nessun brano."}</div>`;
    return `<table class="mu-table"><tbody>${tracks.map((t, i) => mu.row(name, t, i, opts)).join("")}</tbody></table>`;
  };

  mu.refreshRows = () => {
    document.querySelectorAll("#mu-main tr.row").forEach((tr) => {
      const t = (mu.sets[tr.dataset.list] || [])[Number(tr.dataset.i)];
      tr.classList.toggle("now", !!(t && mu.current && mu.current.id === t.id));
    });
  };

  mu.pop = null;
  mu.closePop = () => { if (mu.pop) { mu.pop.remove(); mu.pop = null; } };
  mu.menu = (anchor, items, title) => {
    mu.closePop();
    const box = document.createElement("div");
    box.className = "mu-pop";
    box.innerHTML = (title ? `<div class="sub">${mu.esc(title)}</div>` : "") + items.map((it, i) => (it === "-" ? "<hr>" : `<button data-i="${i}">${mu.esc(it.label)}</button>`)).join("");
    document.body.appendChild(box);
    const r = anchor.getBoundingClientRect();
    box.style.left = `${Math.max(8, Math.min(window.innerWidth - box.offsetWidth - 8, r.right - box.offsetWidth))}px`;
    box.style.top = `${Math.max(8, Math.min(window.innerHeight - box.offsetHeight - 8, r.bottom + 4))}px`;
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-i]");
      if (!b) return;
      const it = items[Number(b.dataset.i)];
      mu.closePop();
      if (it && it.fn) it.fn();
    });
    mu.pop = box;
  };

  const pointed = (e) => e.target.closest("[data-act]");

  mu.act = {
    album: (d) => mu.go("album", d.key),
    artist: (d) => mu.go("artist", d.key),
    playlist: (d) => mu.go("playlist", d.id),
    genre: (d) => mu.go("tracks", { genre: d.name }),
    mix: (d) => mu.go("mix", d.id),
    "play-album": async (d) => {
      try { const a = await mu.get(`/api/music/albums/${encodeURIComponent(d.key)}`); mu.play(a.tracks, 0); } catch (e) { mu.err(e); }
    },
    "play-mix": async (d) => {
      try { const r = await mu.get(`/api/music/mix/${encodeURIComponent(d.id)}`); mu.play(r.tracks, 0); } catch (e) { mu.err(e); }
    },
    play: (d) => { const list = mu.sets[d.list] || []; mu.play(list, Number(d.i)); },
    like: async (d, el) => {
      const t = (mu.sets[d.list] || [])[Number(d.i)];
      if (!t) return;
      try {
        await mu.post(`/api/music/tracks/${t.id}/like`, { on: !t.liked });
        t.liked = !t.liked;
        el.textContent = t.liked ? "♥" : "♡";
        el.classList.toggle("on", t.liked);
        if (mu.current && mu.current.id === t.id) { mu.current.liked = t.liked; mu.syncLike && mu.syncLike(); }
      } catch (e) { mu.err(e); }
    },
    menu: (d, el) => { const t = (mu.sets[d.list] || [])[Number(d.i)]; if (t && mu.trackMenu) mu.trackMenu(el, t, d.list, Number(d.i)); },
    back: () => mu.back(),
  };

  mu.click = (e) => {
    const el = pointed(e);
    if (!el) return;
    const handler = mu.act[el.dataset.act];
    if (!handler) return;
    e.stopPropagation();
    handler(el.dataset, el, e);
  };

  mu.highlight = (name) => {
    document.querySelectorAll("#mu-nav button[data-view]").forEach((b) => b.classList.toggle("on", b.dataset.view === name));
  };

  mu.go = async (name, arg, keep) => {
    if (!keep && mu.view && mu.view.name !== name) mu.stack.push(mu.view);
    if (mu.stack.length > 30) mu.stack.shift();
    mu.view = { name, arg };
    mu.highlight(["album", "artist"].includes(name) ? "albums" : name === "playlist" ? "" : name === "mix" ? "home" : name);
    mu.closePop();
    const render = mu.views[name];
    if (!render) { mu.main().innerHTML = '<div class="mu-empty">Sezione non disponibile.</div>'; return; }
    mu.main().innerHTML = '<div class="faint">Caricamento…</div>';
    try { await render(arg); } catch (e) { mu.main().innerHTML = `<div class="mu-empty">${mu.esc(e.message)}</div>`; }
    window.scrollTo({ top: 0 });
  };

  mu.back = () => { const prev = mu.stack.pop(); if (prev) mu.go(prev.name, prev.arg, true); else mu.go("home", null, true); };
  mu.reload = () => mu.go(mu.view.name, mu.view.arg, true);
  mu.backButton = () => '<button class="btn sm" data-act="back">← Indietro</button>';

  mu.loadConfig = async () => {
    try { mu.cfg = await mu.get("/api/music/library"); } catch (e) { mu.cfg = {}; }
    return mu.cfg;
  };

  function init() {
    $("mu-nav").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-view]");
      if (b) { mu.stack = []; mu.go(b.dataset.view); }
    });
    $("mu-main").addEventListener("click", mu.click);
    $("mu-drawer").addEventListener("click", mu.click);
    document.addEventListener("click", (e) => { if (mu.pop && !mu.pop.contains(e.target) && !e.target.closest(".more, [data-menu]")) mu.closePop(); });
    ["player", "queue", "pl", "out", "manage"].forEach((m) => mu[m] && mu[m].init && mu[m].init());
  }

  function load() {
    if (!mu.ready) { mu.ready = true; mu.go("home", null, true); } else mu.reload();
    if (mu.reloadPlaylists) mu.reloadPlaylists();
    mu.loadConfig().then(() => mu.player.prefs && mu.player.prefs());
    if (mu.player && mu.player.restore) mu.player.restore();
  }

  function onState(s) {
    const key = (s.now_playing && s.now_playing.key) || "";
    if (key !== mu.ambient) { mu.ambient = key; if (A.isOn("music") && mu.view.name === "manage" && mu.views.manage) mu.reload(); }
  }

  A.tab("music", { title: "Musica", init, load, onState, leave() { mu.closePop(); } });
})();
