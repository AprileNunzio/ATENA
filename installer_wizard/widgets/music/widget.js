(() => {
  const safeUrl = (u) => {
    const s = String(u || "").trim();
    return /^(https?:\/\/|\/(?!\/)|data:image\/)/i.test(s) ? s : "";
  };
  function paint(el, d, ctx) {
    const bio = String((d.bio && d.bio.text) || "").slice(0, 1000);
    const cover = safeUrl(d.cover);
    const spot = d.source === "spotify";
    el.innerHTML = `${ctx.head({ icon: "music", label: spot ? "Spotify" : "In ascolto", chip: spot ? "in riproduzione" : "", live: spot })}
      <div class="mu-row">
        <div class="mu-cover">${cover ? `<img src="${ctx.esc(cover)}" alt="">` : ctx.icon("music")}</div>
        <div class="mu-txt"><div class="wk-title mu-title">${ctx.esc(String(d.title ?? "").slice(0, 120))}</div><div class="wk-accent mu-artist">${ctx.esc(String(d.artist || "").slice(0, 120))}</div>
          <div class="wk-faint mu-meta">${ctx.esc([d.album, d.year, d.genre].filter(Boolean).map((x) => String(x).slice(0, 60)).join(" · "))}</div></div>
      </div>
      <div class="mu-prog"><span class="wk-bar mu-track"><i></i></span><span class="wk-mono mu-time"></span></div>
      ${bio ? `<div class="wk-sub mu-bio">${ctx.esc(bio.length > 200 ? bio.slice(0, bio.lastIndexOf(" ", 200)) + "…" : bio)}</div>` : ""}`;
    tick(el, d, ctx);
  }
  function tick(el, d, ctx) {
    const bar = el.querySelector(".mu-track i"), time = el.querySelector(".mu-time");
    if (!bar) return;
    const dur = Number(d.duration) || 0, start = Number(d.started_at) || 0;
    if (!dur || !start) { bar.parentNode.parentNode.style.display = "none"; return; }
    bar.parentNode.parentNode.style.display = "";
    const pos = Math.max(0, Math.min(dur, ctx.now() - start));
    bar.style.width = `${(pos / dur) * 100}%`;
    time.textContent = `${ctx.mmss(pos)} / ${ctx.mmss(dur)}`;
  }
  const timers = new WeakMap();
  const impl = {
    render(el, d, ctx) { paint(el, d, ctx); clearInterval(timers.get(el)); timers.set(el, setInterval(() => tick(el, el._d || d, ctx), 1000)); el._d = d; },
    update(el, d, ctx) { if (!el._d || el._d.key !== d.key) paint(el, d, ctx); el._d = d; tick(el, d, ctx); },
    destroy(el) { clearInterval(timers.get(el)); },
  };
  AtenaDesk.register("music", impl);
})();
