(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 2000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  AtenaDesk.register("audio_spectrum", {
    render(el, d, ctx) {
      const lines = plain(d.content).split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 4);
      const [first = "", ...rest] = lines;
      el.innerHTML = `${ctx.head({ icon: "wave", label: "Spettro audio", chip: lines.length ? "live" : "", live: lines.length > 0 })}
        <div class="as-bars" aria-hidden="true">${"<i></i>".repeat(48)}</div>
        ${first ? `<div class="wk-title">${ctx.esc(first)}</div>${rest.map((l) => `<div class="wk-sub">${ctx.esc(l)}</div>`).join("")}` : `<div class="wk-empty"><span>Nessun audio in ingresso</span></div>`}`;
    },
  });
})();
