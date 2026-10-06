(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const mu = A.mu, esc = mu.esc;
  const P = mu.player = {};
  const KEY = "atena-music";
  const BANDS = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000];
  const PRESETS = {
    "Piatto": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "Bassi forti": [6, 5, 4, 2, 0, 0, 0, 0, 0, 0], "Voce": [-2, -1, 0, 2, 4, 4, 3, 1, 0, -1],
    "Rock": [5, 4, 2, -1, -2, -1, 2, 4, 5, 5], "Classica": [0, 0, 0, 0, 0, 0, -2, -2, -2, -4], "Loudness": [6, 4, 0, 0, -1, 0, -1, 0, 4, 6],
    "Acuti": [0, 0, 0, 0, 0, 2, 4, 5, 6, 6],
  };
  const decks = [new Audio(), new Audio()];
  const Q = { tracks: [], orig: [], index: -1 };
  const S = { shuffle: false, repeat: "off", volume: 0.8, muted: false, speed: 1, eq: Array(10).fill(0), preset: "Piatto", normalize: false, crossfade: 0 };
  let active = 0, ctx = null, gains = [], filters = [], master = null, compressor = null, fadeTimer = null, sleepTimer = null, sleepEnd = 0;
  let listened = 0, lastTime = 0, preloadedFor = null, seeking = false, moreLoading = false, saveAt = 0;
  mu.current = null;

  const deck = () => decks[active];
  const url = (id) => `/api/music/stream/${id}`;
  const save = () => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ ids: Q.tracks.map((t) => t.id).slice(0, 500), index: Q.index, pos: mu.out.remote ? 0 : deck().currentTime, ...S }));
    } catch (err) { console.info("Memoria locale non disponibile", err); }
  };
  const load = () => {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (err) { return null; }
  };

  function graph() {
    if (ctx || !(window.AudioContext || window.webkitAudioContext)) return;
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      master = ctx.createGain();
      compressor = ctx.createDynamicsCompressor();
      compressor.threshold.value = -26; compressor.ratio.value = 4; compressor.attack.value = 0.01; compressor.release.value = 0.25;
      filters = BANDS.map((f, i) => {
        const b = ctx.createBiquadFilter();
        b.type = i === 0 ? "lowshelf" : i === BANDS.length - 1 ? "highshelf" : "peaking";
        b.frequency.value = f; b.Q.value = 1.1; b.gain.value = S.eq[i] || 0;
        return b;
      });
      gains = decks.map((d) => {
        const g = ctx.createGain();
        ctx.createMediaElementSource(d).connect(g);
        g.connect(filters[0]);
        return g;
      });
      filters.reduce((a, b) => { a.connect(b); return b; });
      route();
      decks.forEach((d) => { d.volume = 1; });
      applyVolume();
    } catch (err) {
      console.warn("Audio avanzato non disponibile", err);
      ctx = null;
    }
  }

  function route() {
    if (!ctx) return;
    const last = filters[filters.length - 1];
    try { last.disconnect(); } catch (err) { console.info(err); }
    if (S.normalize) { last.connect(compressor); compressor.connect(master); } else last.connect(master);
    master.connect(ctx.destination);
  }

  function applyVolume() {
    const v = S.muted ? 0 : S.volume;
    if (ctx) master.gain.value = v ** 1.6;
    else decks.forEach((d) => { d.volume = v; });
  }

  P.eq = {
    bands: BANDS, presets: PRESETS,
    state: () => ({ gains: S.eq.slice(), preset: S.preset, normalize: S.normalize }),
    set(i, db) { S.eq[i] = db; S.preset = "Personalizzato"; if (filters[i]) filters[i].gain.value = db; save(); },
    preset(name) { if (!PRESETS[name]) return; S.eq = PRESETS[name].slice(); S.preset = name; filters.forEach((f, i) => { f.gain.value = S.eq[i]; }); save(); },
    normalize(on) { S.normalize = !!on; route(); save(); },
  };

  P.prefs = () => {
    const saved = load();
    if (!saved || saved.crossfade === undefined) S.crossfade = Number((mu.cfg.prefs || {}).crossfade) || 0;
  };
  P.crossfade = (s) => { S.crossfade = Math.max(0, Math.min(12, Number(s) || 0)); save(); };
  P.state = () => ({ ...S });
  P.queue = () => ({ tracks: Q.tracks, index: Q.index });

  function shuffled(list, keep) {
    const rest = list.filter((t) => t !== keep);
    for (let i = rest.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [rest[i], rest[j]] = [rest[j], rest[i]]; }
    return keep ? [keep, ...rest] : rest;
  }

  function setQueue(tracks, index, shuffle) {
    if (shuffle && index === 0 && tracks.length > 1) index = Math.floor(Math.random() * tracks.length);
    Q.orig = tracks.slice();
    Q.tracks = shuffle ? shuffled(tracks, tracks[index]) : tracks.slice();
    Q.index = shuffle ? 0 : index;
    if (shuffle) S.shuffle = true;
  }

  function report(done) {
    const t = mu.current;
    if (t && listened >= 5 && !mu.out.remote) mu.post(`/api/music/tracks/${t.id}/played`, { seconds: Math.round(listened), done: !!done, source: "web" }).catch((err) => console.info(err));
    listened = 0;
  }

  function paint() {
    const bar = $("mu-bar");
    if (!bar) return;
    const t = mu.current;
    bar.classList.toggle("show", !!t);
    document.body.style.setProperty("--mu-pad", t ? "92px" : "0px");
    if (!t) return;
    $("mu-now").innerHTML = `${t.cover ? `<img src="${mu.cover(t.album_key, 96)}" alt="" data-act="album" data-key="${esc(t.album_key)}" onerror="this.outerHTML='<div class=ph>♪</div>'">` : '<div class="ph">♪</div>'}
      <div class="tt">${mu.out.remote ? `<em>Su ${esc(mu.out.name)}</em>` : ""}<b data-act="album" data-key="${esc(t.album_key)}">${esc(t.title)}</b><small data-act="artist" data-key="${esc(t.artist_key)}" style="cursor:pointer">${esc(t.artist)}</small></div>
      <button class="ic" id="mu-like" style="background:none;border:0;cursor:pointer;color:${t.liked ? "var(--red)" : "var(--text-faint)"};font-size:18px">${t.liked ? "♥" : "♡"}</button>`;
    $("mu-dur").textContent = mu.time(t.duration);
    document.title = `${t.title} · ${t.artist}`;
    mu.refreshRows();
    if (mu.queue && mu.queue.refresh) mu.queue.refresh();
    media();
  }

  mu.syncLike = () => { const b = $("mu-like"); if (b && mu.current) { b.textContent = mu.current.liked ? "♥" : "♡"; b.style.color = mu.current.liked ? "var(--red)" : "var(--text-faint)"; } };

  function buttons() {
    const playing = P.playing();
    $("mu-play").textContent = playing ? "❚❚" : "▶";
    $("mu-shuffle").classList.toggle("on", S.shuffle);
    $("mu-repeat").classList.toggle("on", S.repeat !== "off");
    $("mu-repeat").textContent = S.repeat === "one" ? "⟲¹" : "⟲";
    $("mu-mute").textContent = S.muted || S.volume === 0 ? "🔇" : "🔊";
    $("mu-out").classList.toggle("on", mu.out.remote);
    $("mu-out").title = `Riproduci su: ${mu.out.name}`;
  }

  P.playing = () => (mu.out.remote ? !!(mu.remoteState && mu.remoteState.state === "playing") : !deck().paused && !deck().ended);

  function media() {
    if (!("mediaSession" in navigator) || !mu.current) return;
    const t = mu.current;
    navigator.mediaSession.metadata = new MediaMetadata({ title: t.title, artist: t.artist, album: t.album,
      artwork: t.cover ? [{ src: new URL(mu.cover(t.album_key, 600), location.href).href, sizes: "600x600", type: "image/jpeg" }] : [] });
  }

  async function startTrack(i, start = 0, fade = 0) {
    const t = Q.tracks[i];
    if (!t) return P.stop();
    report(false);
    graph();
    if (ctx && ctx.state === "suspended") ctx.resume().catch((err) => console.info(err));
    Q.index = i;
    mu.current = t;
    const from = deck();
    const to = fade && ctx ? decks[1 - active] : from;
    if (to.dataset.id !== String(t.id)) { to.src = url(t.id); to.dataset.id = String(t.id); }
    to.playbackRate = S.speed;
    try { to.currentTime = start; } catch (err) { console.info(err); }
    clearTimeout(fadeTimer);
    if (ctx) {
      const now = ctx.currentTime;
      const next = decks.indexOf(to);
      gains.forEach((g, n) => { g.gain.cancelScheduledValues(now); g.gain.setValueAtTime(g.gain.value, now); });
      if (fade && to !== from) {
        gains[next].gain.setValueAtTime(0, now); gains[next].gain.linearRampToValueAtTime(1, now + fade);
        gains[active].gain.linearRampToValueAtTime(0, now + fade);
        const old = from;
        fadeTimer = setTimeout(() => old.pause(), fade * 1000 + 100);
      } else {
        gains[next].gain.setValueAtTime(1, now);
        if (to !== from) from.pause();
      }
    } else if (to !== from) from.pause();
    active = decks.indexOf(to);
    preloadedFor = null;
    lastTime = start;
    paint();
    try { await to.play(); } catch (err) { A.toast("Impossibile avviare la riproduzione: tocca play", true); }
    buttons();
    save();
    if (mu.queue && mu.queue.loadLyrics) mu.queue.loadLyrics();
  }

  function hasNext() { return Q.index + 1 < Q.tracks.length || S.repeat !== "off"; }

  async function ensureMore() {
    if (moreLoading || !mu.cfg.prefs || !mu.cfg.prefs.radio || S.repeat !== "off" || !Q.tracks.length || Q.index < Q.tracks.length - 2) return;
    moreLoading = true;
    try {
      const seed = Q.tracks[Q.tracks.length - 1];
      const r = await mu.post("/api/music/radio", { seed: seed.id, exclude: Q.tracks.map((t) => t.id).slice(-300) });
      const have = new Set(Q.tracks.map((t) => t.id));
      const fresh = r.tracks.filter((t) => !have.has(t.id));
      Q.tracks.push(...fresh);
      Q.orig.push(...fresh);
      if (mu.queue && mu.queue.refresh) mu.queue.refresh();
    } catch (err) { console.info("Radio non disponibile", err); } finally { moreLoading = false; }
  }

  async function advance(auto, fade = 0) {
    if (mu.out.remote) return mu.out.control("next");
    report(auto);
    if (auto && S.repeat === "one") return startTrack(Q.index, 0, 0);
    if (Q.index + 1 >= Q.tracks.length && S.repeat === "off") await ensureMore();
    let next = Q.index + 1;
    if (next >= Q.tracks.length) { if (S.repeat === "all" && Q.tracks.length) next = 0; else return P.stop(); }
    return startTrack(next, 0, fade);
  }

  function preload() {
    const next = Q.tracks[Q.index + 1];
    if (!next || preloadedFor === next.id) return;
    preloadedFor = next.id;
    const other = decks[1 - active];
    other.preload = "auto";
    other.src = url(next.id);
    other.dataset.id = String(next.id);
  }

  function onTime() {
    const d = deck();
    if (mu.out.remote || !mu.current) return;
    const dt = d.currentTime - lastTime;
    if (dt > 0 && dt < 2 && !d.paused) listened += dt;
    lastTime = d.currentTime;
    const total = d.duration || mu.current.duration || 0;
    if (!seeking && total) { $("mu-seek").value = String(Math.round((d.currentTime / total) * 1000)); $("mu-cur").textContent = mu.time(d.currentTime); $("mu-dur").textContent = mu.time(total); }
    const left = total - d.currentTime;
    if (total && left < 30) { ensureMore(); if (left < 20) preload(); }
    if (S.crossfade > 0 && ctx && total > S.crossfade * 3 && left <= S.crossfade && left > 0.3 && hasNext() && Q.index + 1 < Q.tracks.length && S.repeat !== "one") advance(false, S.crossfade);
    if (mu.queue && mu.queue.tick) mu.queue.tick(d.currentTime);
    if (Date.now() - saveAt > 5000) { saveAt = Date.now(); save(); }
  }

  P.play = (tracks, index = 0, opts = {}) => {
    if (!tracks || !tracks.length) return;
    if (mu.out.remote) { setQueue(tracks, index, !!opts.shuffle); return mu.out.start(Q.tracks.map((t) => t.id), Q.index, opts.start || 0); }
    setQueue(tracks, index, !!opts.shuffle);
    buttons();
    return startTrack(Q.index, opts.start || 0, 0);
  };

  P.enqueue = (tracks, next = false) => {
    if (!tracks.length) return;
    if (!Q.tracks.length) return P.play(tracks, 0);
    const at = next ? Q.index + 1 : Q.tracks.length;
    Q.tracks.splice(at, 0, ...tracks);
    Q.orig.push(...tracks);
    A.toast(next ? "Riprodotto subito dopo" : `Aggiunti alla coda: ${tracks.length}`);
    if (mu.queue && mu.queue.refresh) mu.queue.refresh();
    save();
  };

  P.jump = (i) => { if (mu.out.remote) { Q.index = i; return mu.out.start(Q.tracks.map((t) => t.id), i, 0); } return startTrack(i, 0, 0); };
  P.removeAt = (i) => {
    if (i === Q.index) return;
    Q.tracks.splice(i, 1);
    if (i < Q.index) Q.index -= 1;
    if (mu.queue && mu.queue.refresh) mu.queue.refresh();
    save();
  };
  P.moveInQueue = (from, to) => {
    if (from === Q.index || to < 0 || to >= Q.tracks.length) return;
    const [t] = Q.tracks.splice(from, 1);
    Q.tracks.splice(to, 0, t);
    if (from < Q.index && to >= Q.index) Q.index -= 1; else if (from > Q.index && to <= Q.index) Q.index += 1;
    if (mu.queue && mu.queue.refresh) mu.queue.refresh();
  };
  P.clear = () => { P.stop(); Q.tracks = []; Q.orig = []; Q.index = -1; mu.current = null; paint(); if (mu.queue && mu.queue.refresh) mu.queue.refresh(); save(); };

  P.stop = () => {
    report(false);
    decks.forEach((d) => d.pause());
    buttons();
  };

  P.toggle = () => {
    if (mu.out.remote) return mu.out.control(P.playing() ? "pause" : "resume");
    const d = deck();
    if (!mu.current && Q.tracks.length) return startTrack(Math.max(0, Q.index), 0, 0);
    if (!mu.current) return null;
    graph();
    if (ctx && ctx.state === "suspended") ctx.resume().catch((err) => console.info(err));
    return d.paused ? d.play().then(buttons).catch(() => A.toast("Riproduzione non riuscita", true)) : (d.pause(), buttons());
  };

  P.position = () => deck().currentTime;
  P.pauseLocal = () => { decks.forEach((d) => d.pause()); buttons(); };
  P.next = () => advance(false, 0);
  P.prev = () => {
    if (mu.out.remote) return mu.out.control("prev");
    if (deck().currentTime > 4 || Q.index <= 0) { deck().currentTime = 0; return null; }
    return startTrack(Q.index - 1, 0, 0);
  };
  P.seekTo = (seconds) => { if (mu.out.remote) return mu.out.control("seek", seconds); deck().currentTime = Math.max(0, seconds); return null; };
  P.volume = (v) => { S.volume = Math.max(0, Math.min(1, v)); S.muted = false; applyVolume(); buttons(); save(); if (mu.out.remote) mu.out.control("volume", S.volume); };
  P.mute = () => { S.muted = !S.muted; applyVolume(); buttons(); };
  P.toggleShuffle = () => {
    S.shuffle = !S.shuffle;
    const cur = Q.tracks[Q.index];
    if (S.shuffle) { const before = Q.tracks.slice(0, Q.index + 1); Q.tracks = [...before, ...shuffled(Q.tracks.slice(Q.index + 1))]; }
    else { const rest = new Set(Q.tracks.slice(Q.index + 1)); Q.tracks = [...Q.tracks.slice(0, Q.index + 1), ...Q.orig.filter((t) => rest.has(t))]; }
    Q.index = Q.tracks.indexOf(cur);
    buttons();
    if (mu.queue && mu.queue.refresh) mu.queue.refresh();
    save();
  };
  P.cycleRepeat = () => { S.repeat = S.repeat === "off" ? "all" : S.repeat === "all" ? "one" : "off"; buttons(); save(); if (mu.out.remote) mu.out.control("repeat"); };
  P.speed = (v) => { S.speed = v; decks.forEach((d) => { d.playbackRate = v; }); save(); };

  P.sleep = (minutes) => {
    clearTimeout(sleepTimer);
    sleepEnd = 0;
    if (!minutes) { A.toast("Timer di spegnimento annullato"); return; }
    if (minutes === "track") { sleepEnd = -1; A.toast("La musica si fermerà alla fine del brano"); return; }
    sleepEnd = Date.now() + minutes * 60000;
    sleepTimer = setTimeout(() => { fadeOut(); }, minutes * 60000);
    A.toast(`La musica si fermerà tra ${minutes} minuti`);
  };
  P.sleepLeft = () => (sleepEnd > 0 ? Math.max(0, Math.round((sleepEnd - Date.now()) / 60000)) : sleepEnd === -1 ? -1 : 0);

  function fadeOut() {
    sleepEnd = 0;
    if (mu.out.remote) { mu.out.control("pause"); return; }
    const before = S.volume;
    let step = 0;
    const timer = setInterval(() => {
      step += 1;
      S.volume = before * (1 - step / 20);
      applyVolume();
      if (step >= 20) { clearInterval(timer); deck().pause(); S.volume = before; applyVolume(); buttons(); A.toast("Buonanotte: musica fermata"); }
    }, 150);
  }

  P.remoteApply = (view) => {
    mu.remoteState = view;
    if (view.queue && view.queue.length) { Q.tracks = view.queue; Q.orig = view.queue.slice(); Q.index = view.index; }
    mu.current = view.track || mu.current;
    S.repeat = view.repeat || S.repeat;
    if (view.duration) { $("mu-seek").value = String(Math.round((view.position / view.duration) * 1000)); $("mu-dur").textContent = mu.time(view.duration); }
    $("mu-cur").textContent = mu.time(view.position || 0);
    paint();
    buttons();
    if (mu.queue && mu.queue.tick) mu.queue.tick(view.position || 0);
  };

  P.restore = async () => {
    if (mu.current || Q.tracks.length) return;
    const saved = load();
    if (!saved || !saved.ids || !saved.ids.length) return;
    try {
      const r = await mu.get(`/api/music/tracks/lookup?ids=${saved.ids.join(",")}`);
      if (!r.tracks.length) return;
      Q.tracks = r.tracks; Q.orig = r.tracks.slice();
      Q.index = Math.min(r.tracks.length - 1, Math.max(0, saved.index || 0));
      mu.current = Q.tracks[Q.index];
      const d = deck();
      d.src = url(mu.current.id); d.dataset.id = String(mu.current.id);
      d.addEventListener("loadedmetadata", () => { if (saved.pos > 0 && saved.pos < d.duration) d.currentTime = saved.pos; }, { once: true });
      paint();
      buttons();
    } catch (err) { console.info("Coda precedente non ripristinata", err); }
  };

  function keys(e) {
    if (!A.isOn("music") || e.ctrlKey || e.metaKey || e.altKey) return;
    const el = document.activeElement;
    if (el && ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) && el.type !== "range") return;
    const k = e.key;
    const map = {
      " ": () => P.toggle(), ArrowRight: () => (e.shiftKey ? P.next() : P.seekTo(deck().currentTime + 10)), ArrowLeft: () => (e.shiftKey ? P.prev() : P.seekTo(deck().currentTime - 10)),
      ArrowUp: () => P.volume(S.volume + 0.05), ArrowDown: () => P.volume(S.volume - 0.05), m: () => P.mute(), n: () => P.next(), p: () => P.prev(),
      s: () => P.toggleShuffle(), r: () => P.cycleRepeat(),
      l: () => { if (mu.current) { mu.sets.__current = [mu.current]; mu.act.like({ list: "__current", i: "0" }, $("mu-like") || document.createElement("b")); } },
    };
    if (!map[k]) return;
    e.preventDefault();
    map[k]();
  }

  function build() {
    const bar = document.createElement("div");
    bar.className = "mu-bar";
    bar.id = "mu-bar";
    bar.innerHTML = `<div class="mu-now" id="mu-now"></div>
      <div class="mu-ctl"><div class="mu-btns"><button id="mu-shuffle" title="Casuale (S)">⤮</button><button id="mu-prev" title="Precedente (P)">⏮</button>
        <button id="mu-play" class="play" title="Play/Pausa (spazio)">▶</button><button id="mu-next" title="Successivo (N)">⏭</button><button id="mu-repeat" title="Ripeti (R)">⟲</button></div>
        <div class="mu-seek"><span id="mu-cur">0:00</span><input type="range" id="mu-seek" min="0" max="1000" value="0"><span id="mu-dur">0:00</span></div></div>
      <div class="mu-extra"><button id="mu-lyrics" title="Testo">♬</button><button id="mu-queue" title="Coda">☰</button><button id="mu-eq" title="Equalizzatore">🎚</button>
        <button id="mu-out" title="Dispositivi">📡</button><button id="mu-more" title="Velocità e timer">⏲</button><button id="mu-mute">🔊</button>
        <input type="range" id="mu-vol" min="0" max="100" value="80" title="Volume"></div>`;
    document.body.appendChild(bar);
    $("mu-play").addEventListener("click", () => P.toggle());
    $("mu-next").addEventListener("click", () => P.next());
    $("mu-prev").addEventListener("click", () => P.prev());
    $("mu-shuffle").addEventListener("click", () => P.toggleShuffle());
    $("mu-repeat").addEventListener("click", () => P.cycleRepeat());
    $("mu-mute").addEventListener("click", () => P.mute());
    $("mu-vol").addEventListener("input", (e) => P.volume(Number(e.target.value) / 100));
    $("mu-seek").addEventListener("input", () => { seeking = true; const t = mu.current; if (t) $("mu-cur").textContent = mu.time((Number($("mu-seek").value) / 1000) * (deck().duration || t.duration)); });
    $("mu-seek").addEventListener("change", () => { const t = mu.current; if (t) P.seekTo((Number($("mu-seek").value) / 1000) * ((mu.out.remote ? mu.remoteState.duration : deck().duration) || t.duration)); seeking = false; });
    $("mu-queue").addEventListener("click", () => mu.queue.open("queue"));
    $("mu-lyrics").addEventListener("click", () => mu.queue.open("lyrics"));
    $("mu-eq").addEventListener("click", () => mu.queue.open("eq"));
    $("mu-out").addEventListener("click", (e) => mu.out.picker && mu.out.picker(e.currentTarget));
    $("mu-more").addEventListener("click", (e) => {
      const speeds = [0.75, 1, 1.25, 1.5, 2].map((v) => ({ label: `Velocità ${v}×${S.speed === v ? " ✓" : ""}`, fn: () => P.speed(v) }));
      const sleeps = [15, 30, 60].map((m) => ({ label: `Spegni tra ${m} minuti`, fn: () => P.sleep(m) }));
      mu.menu(e.currentTarget, [...speeds, "-", ...sleeps, { label: "Spegni a fine brano", fn: () => P.sleep("track") }, { label: "Annulla il timer", fn: () => P.sleep(0) }],
        P.sleepLeft() > 0 ? `Timer: ${P.sleepLeft()} min` : "Velocità e timer");
    });
    $("mu-now").addEventListener("click", (e) => {
      if (e.target.id === "mu-like" && mu.current) {
        mu.post(`/api/music/tracks/${mu.current.id}/like`, { on: !mu.current.liked }).then(() => { mu.current.liked = !mu.current.liked; mu.syncLike(); }).catch(mu.err);
        return;
      }
      mu.click(e);
    });
  }

  P.init = () => {
    build();
    const saved = load();
    if (saved) Object.keys(S).forEach((k) => { if (saved[k] !== undefined) S[k] = saved[k]; });
    $("mu-vol").value = String(Math.round(S.volume * 100));
    applyVolume();
    decks.forEach((d) => {
      d.preload = "auto";
      d.addEventListener("timeupdate", () => { if (d === deck()) onTime(); });
      d.addEventListener("ended", () => { if (d === deck()) { if (sleepEnd === -1) { sleepEnd = 0; report(true); buttons(); A.toast("Musica fermata a fine brano"); return; } advance(true); } });
      d.addEventListener("play", buttons);
      d.addEventListener("pause", buttons);
      d.addEventListener("error", () => {
        if (d !== deck() || !mu.current || !d.src) return;
        A.toast(`Non riesco a riprodurre «${mu.current.title}»: passo al prossimo`, true);
        if (hasNext()) advance(true);
      });
    });
    document.addEventListener("keydown", keys);
    if ("mediaSession" in navigator) {
      const set = (name, fn) => { try { navigator.mediaSession.setActionHandler(name, fn); } catch (err) { console.info(name, err); } };
      set("play", () => P.toggle()); set("pause", () => P.toggle()); set("nexttrack", () => P.next()); set("previoustrack", () => P.prev());
      set("seekto", (d) => P.seekTo(d.seekTime || 0));
    }
    buttons();
    mu.play = P.play;
    mu.enqueue = P.enqueue;
    mu.radioFrom = async (track) => {
      try { const r = await mu.post("/api/music/radio", { seed: track.id, exclude: [] }); P.play([track, ...r.tracks], 0); } catch (e) { mu.err(e); }
    };
    mu.current = null;
  };

  mu.play = P.play;
  mu.enqueue = P.enqueue;
  mu.syncPlayer = () => { buttons(); paint(); };
})();
