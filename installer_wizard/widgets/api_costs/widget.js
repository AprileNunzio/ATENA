(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 6000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  const body = (content, ctx) => {
    const lines = plain(content).split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 10);
    if (!lines.length) return `<div class="wk-empty"><span>In attesa di dati</span></div>`;
    const pairs = lines.map((l) => l.match(/^([^:]{1,32}):\s+(.+)$/));
    if (!pairs.every(Boolean)) return `<p class="wk-text">${lines.map((l) => ctx.esc(l)).join("<br>")}</p>`;
    const [first, ...rest] = pairs;
    const hero = first[2].length <= 14;
    const items = hero ? rest : pairs;
    const pc = first[2].match(/(\d+(?:[.,]\d+)?)\s*%/);
    const level = pc ? Number(pc[1].replace(",", ".")) : null;
    return `${hero ? `<div class="wk-hero"><span class="wk-num sm">${ctx.esc(first[2])}</span><span class="wk-sub">${ctx.esc(first[1])}</span></div>${level === null ? "" : ctx.bar(level, level >= 90 ? "bad" : level >= 75 ? "warn" : "")}` : ""}
      ${items.length ? `<dl class="wk-kv">${items.map((p) => `<dt>${ctx.esc(p[1])}</dt><dd class="mono">${ctx.esc(p[2])}</dd>`).join("")}</dl>` : ""}`;
  };
  AtenaDesk.register("api_costs", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "coin", label: "Costi API" })}${body(d.content, ctx)}`;
    },
  });
})();
