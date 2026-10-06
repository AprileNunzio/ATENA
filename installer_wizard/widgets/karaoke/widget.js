(() => {
  const timers = new WeakMap();

  function lines(d) {
    const ly = d.lyrics || {};
    return Array.isArray(ly.synced) && ly.synced.length ? ly.synced.slice(0, 400) : null;
  }

  function paint(el, d, ctx) {
    const synced = lines(d);
    const name = [d.title, d.artist].filter(Boolean).map((x) => String(x).slice(0, 80)).join(" — ");
    const head = ctx.head({ icon: "mic", label: "Karaoke", title: name, chip: synced ? "sincronizzato" : "", live: !!synced });
    if (!synced) {
      el._lines = null;
      const plain = String((d.lyrics && d.lyrics.plain) || "").slice(0, 8000);
      el.innerHTML = head + (plain
        ? `<div class="ka-plain">${ctx.esc(plain)}</div>`
        : `<div class="wk-empty">Testo non disponibile per questo brano.</div>`);
      return;
    }
    el.innerHTML = head + `<div class="ka-lines">${synced.map((l, i) =>
      `<div class="ka-line" data-i="${i}">${ctx.esc(String((l && l.text) || "· · ·").slice(0, 200))}</div>`).join("")}</div>`;
    el._lines = synced;
    tick(el, d, ctx);
  }

  function tick(el, d, ctx) {
    const synced = el._lines;
    if (!synced || !d.started_at) return;
    const pos = ctx.now() - Number(d.started_at);
    let cur = -1;
    for (let i = 0; i < synced.length; i++) { if (Number(synced[i].t) <= pos + 0.25) cur = i; else break; }
    const box = el.querySelector(".ka-lines");
    const nodes = el.querySelectorAll(".ka-line");
    nodes.forEach((n, i) => {
      n.classList.toggle("on", i === cur);
      n.classList.toggle("past", i < cur);
    });
    if (cur >= 0 && box && nodes[cur]) {
      const off = nodes[cur].offsetTop - box.clientHeight / 2 + nodes[cur].offsetHeight / 2;
      box.scrollTo({ top: Math.max(0, off), behavior: "smooth" });
    }
  }

  const impl = {
    render(el, d, ctx) {
      paint(el, d, ctx);
      clearInterval(timers.get(el));
      timers.set(el, setInterval(() => tick(el, el._d || d, ctx), 500));
      el._d = d;
    },
    update(el, d, ctx) {
      if (!el._d || el._d.key !== d.key) paint(el, d, ctx);
      el._d = d;
      tick(el, d, ctx);
    },
    destroy(el) { clearInterval(timers.get(el)); },
  };
  AtenaDesk.register("karaoke", impl);
})();
