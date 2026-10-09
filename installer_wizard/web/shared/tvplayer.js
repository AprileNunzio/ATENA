(() => {
  const loaded = {};
  const load = (src) => loaded[src] || (loaded[src] = new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = () => fail(new Error(`libreria ${src} non disponibile`));
    document.head.appendChild(s);
  }));

  async function asHls(video, src) {
    const native = () => { video.src = src; return { destroy() { video.removeAttribute("src"); video.load(); } }; };
    try { await load("/vendor/hls.min.js"); } catch (err) { if (video.canPlayType("application/vnd.apple.mpegurl")) return native(); throw err; }
    if (!window.Hls || !window.Hls.isSupported()) {
      if (video.canPlayType("application/vnd.apple.mpegurl")) return native();
      throw new Error("HLS non supportato");
    }
    const hls = new window.Hls({ lowLatencyMode: true, backBufferLength: 30 });
    hls.loadSource(src); hls.attachMedia(video);
    return new Promise((ok, fail) => {
      hls.on(window.Hls.Events.MANIFEST_PARSED, () => ok(hls));
      hls.on(window.Hls.Events.ERROR, (_, data) => { if (data.fatal) { hls.destroy(); fail(new Error(data.details || "errore HLS")); } });
    });
  }

  async function asTs(video, src) {
    await load("/vendor/mpegts.js");
    if (!window.mpegts || !window.mpegts.isSupported()) throw new Error("flusso TS non supportato");
    const player = window.mpegts.createPlayer({ type: "mpegts", isLive: true, url: new URL(src, location.href).href }, { enableWorker: true, liveBufferLatencyChasing: true });
    player.attachMediaElement(video); player.load();
    return player;
  }

  async function play(video, src, onState) {
    const say = (s) => onState && onState(s);
    say("loading");
    let handle = null;
    try { handle = await asHls(video, src); }
    catch (hlsErr) {
      try { handle = await asTs(video, src); }
      catch (tsErr) { say("error"); throw new Error(`${hlsErr.message} · ${tsErr.message}`); }
    }
    video.muted = false;
    try { await video.play(); } catch { video.muted = true; await video.play().catch(() => say("blocked")); }
    say("playing");
    return { stop() { try { handle.destroy(); } catch { video.pause(); } } };
  }

  window.AtenaTv = { play };
})();
