(() => {
  const players = new WeakMap();
  const STATE = { loading: "in collegamento", playing: "in onda", blocked: "audio disattivato", error: "non disponibile" };

  function ensure(src) {
    if (window.AtenaTv) return Promise.resolve();
    return new Promise((ok, fail) => {
      const s = document.createElement("script");
      s.src = src; s.onload = ok; s.onerror = () => fail(new Error("lettore non disponibile"));
      document.head.appendChild(s);
    });
  }

  AtenaDesk.register("tv_player", {
    render(el, d, ctx) {
      const current = players.get(el);
      if (current && current.src === d.src) return;
      if (current) current.handle && current.handle.stop();
      el.innerHTML = `${ctx.head({ icon: "video", label: "TV", title: d.name || "", chip: "in collegamento", live: true })}
        <div class="tv-frame"><video playsinline></video><div class="tv-msg"></div></div>
        ${d.group ? `<div class="wk-sub">${ctx.esc(d.group)}</div>` : ""}`;
      const video = el.querySelector("video"), chip = el.querySelector(".wk-chip"), msg = el.querySelector(".tv-msg");
      const entry = { src: d.src, handle: null };
      players.set(el, entry);
      if (!d.src) { msg.textContent = "Nessun canale"; return; }
      ensure("/static/shared/tvplayer.js")
        .then(() => window.AtenaTv.play(video, d.src, (s) => { if (chip) chip.textContent = STATE[s] || s; }))
        .then((h) => { entry.handle = h; })
        .catch((e) => { msg.textContent = `Il canale non si apre: ${e.message}`; });
    },
  });
})();
