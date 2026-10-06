(() => {
  const D = window.AtenaDisplay;
  const KEY = "atena-music-device";
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  let id = "";
  try {
    id = localStorage.getItem(KEY) || "";
    if (!id) { id = Math.random().toString(36).slice(2, 10); localStorage.setItem(KEY, id); }
  } catch (err) { id = `t${Math.random().toString(36).slice(2, 9)}`; }
  const device = `display:${id}`;
  const node = new URLSearchParams(location.search).get("node");
  const name = node ? `Schermo ${node}` : D.local ? "Schermo di Atena" : `Schermo ${id.slice(0, 4)}`;
  let audio = null, target = 0.6, reported = 0;

  const post = (state, ended) => {
    if (!audio) return;
    fetch("/api/music/out/report", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device, state, position: audio.currentTime || 0, ended: !!ended }) }).catch(() => {});
  };

  function ensure() {
    if (audio) return audio;
    audio = new Audio();
    audio.preload = "auto";
    audio.addEventListener("ended", () => post("stopped", true));
    audio.addEventListener("error", () => { if (audio.src) setTimeout(() => post("stopped", true), 800); });
    audio.addEventListener("timeupdate", () => {
      if (Date.now() - reported < 3000 || audio.paused) return;
      reported = Date.now();
      post("playing", false);
    });
    return audio;
  }

  const ducked = () => (D.isSpeaking && D.isSpeaking() ? 0.25 : 1);
  setInterval(() => { if (audio && !audio.paused) audio.volume = Math.max(0, Math.min(1, target * ducked())); }, 400);

  function run(cmd) {
    const a = ensure();
    if (cmd.type === "load") {
      target = typeof cmd.volume === "number" ? cmd.volume : target;
      a.src = cmd.url;
      a.currentTime = cmd.start || 0;
      a.volume = target;
      a.play().catch((err) => console.warn("Riproduzione sul display non avviata", err));
    } else if (cmd.type === "pause") { a.pause(); post("paused", false); }
    else if (cmd.type === "resume") { a.play().catch((err) => console.warn(err)); }
    else if (cmd.type === "stop") { a.pause(); a.removeAttribute("src"); a.load(); }
    else if (cmd.type === "seek") { a.currentTime = Math.max(0, Number(cmd.value) || 0); }
    else if (cmd.type === "volume") { target = Math.max(0, Math.min(1, Number(cmd.value) || 0)); a.volume = target; }
  }

  async function loop() {
    for (;;) {
      try {
        const r = await fetch(`/api/music/out/poll?device=${encodeURIComponent(device)}&name=${encodeURIComponent(name)}`, { cache: "no-store" });
        if (r.status === 401 || r.status === 403) { await sleep(60000); continue; }
        if (!r.ok) { await sleep(8000); continue; }
        const d = await r.json();
        if (d.idle) await sleep(d.idle * 1000);
        else if (d.command) run(d.command);
      } catch (err) { await sleep(8000); }
    }
  }

  D.startMusicOut = () => { if (!D.musicOutOn) { D.musicOutOn = true; setTimeout(loop, 4000); } };
  D.startMusicOut();
})();
