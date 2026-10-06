(() => {
  const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).catch(() => {});

  function stop(el) {
    const img = el.querySelector("img");
    if (img) img.src = "";
  }

  function start(el, d, ctx) {
    const img = el.querySelector("img");
    const note = el.querySelector(".lc-note");
    img.onload = () => { note.hidden = true; };
    img.onerror = () => { note.hidden = false; note.textContent = "Immagine non disponibile"; };
    img.src = `/api/cameras/live/${encodeURIComponent(d.source)}.mjpg?t=${Date.now()}`;
  }

  const impl = {
    render(el, d, ctx) {
      el.innerHTML = `<div class="lc"><img alt="${ctx.esc(d.name || "Webcam")}" draggable="false">
        <div class="lc-bar"><span class="lc-live">● LIVE</span><b>${ctx.esc(d.name || "Webcam")}</b>
          <button type="button" data-act="full" title="Tutto schermo">⤢</button><button type="button" data-act="close" title="Chiudi">✕</button></div>
        <div class="lc-note">Collegamento…</div></div>`;
      const key = `live:${d.source}`;
      el.addEventListener("click", (e) => {
        const act = e.target.closest("[data-act]");
        if (!act) return;
        const full = !el.closest(".widget").classList.contains("fullscreen");
        if (act.dataset.act === "close") post("/api/desk/close", { key });
        else post("/api/desk/fullscreen", { key, on: full });
      });
      start(el, d, ctx);
    },
    update() {},
    destroy(el) { stop(el); },
  };
  AtenaDesk.register("live_cam", impl);
})();
