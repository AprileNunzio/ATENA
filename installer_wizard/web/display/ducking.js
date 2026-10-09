(() => {
  const D = window.AtenaDisplay;
  const BEAT_MS = 5000, LOCAL = 0.25, TALKING = new Set(["listening", "transcribing", "thinking", "speaking"]);
  let on = false, sent = 0;

  const talking = () => {
    const ear = window.atenaEar ? window.atenaEar.state : "";
    return TALKING.has(ear) || !!(D.isSpeaking && D.isSpeaking()) || !!D.busy || document.body.classList.contains("conversing");
  };

  function local(duck) {
    document.querySelectorAll(".desk video, .desk audio").forEach((m) => {
      if (duck && m.dataset.duckFrom === undefined) { m.dataset.duckFrom = String(m.volume); m.volume = Math.max(0, m.volume * LOCAL); }
      if (!duck && m.dataset.duckFrom !== undefined) {
        if (Math.abs(m.volume - Number(m.dataset.duckFrom) * LOCAL) < 0.05) m.volume = Number(m.dataset.duckFrom);
        delete m.dataset.duckFrom;
      }
    });
  }

  function signal(value) {
    sent = Date.now();
    fetch("/api/conversation/duck", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: value }) })
      .catch((err) => console.warn("Segnale di conversazione non inviato:", err));
  }

  setInterval(() => {
    const now = talking();
    if (now) local(true);
    if (now && (!on || Date.now() - sent > BEAT_MS)) signal(true);
    if (!now && on) { signal(false); local(false); }
    on = now;
  }, 1000);
})();
