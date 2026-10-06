(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 6000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  const state = (v) => {
    if (/unhealthy|exited|dead|error|errore|stopped|fermo/i.test(v)) return "bad";
    if (/restarting|paused|riavvio|in pausa|starting/i.test(v)) return "warn";
    if (/running|healthy|\bup\b|attivo|in esecuzione/i.test(v)) return "ok";
    return "";
  };
  AtenaDesk.register("docker_matrix", {
    render(el, d, ctx) {
      const lines = plain(d.content).split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 12);
      const pairs = lines.map((l) => l.match(/^([^:]{1,48}):\s+(.+)$/));
      const states = pairs.map((p) => (p ? state(p[2]) : ""));
      const up = states.filter((s) => s === "ok").length;
      const down = states.filter((s) => s === "bad").length;
      const rows = lines.map((l, i) => {
        const p = pairs[i];
        const s = states[i];
        return p
          ? `<li class="wk-row ic${s && s !== "ok" ? ` ${s}` : ""}">${ctx.icon("container")}<span><b>${ctx.esc(p[1])}</b></span><span class="wk-chip${s ? ` ${s}` : ""}">${ctx.esc(p[2])}</span></li>`
          : `<li class="wk-row"><span><b>${ctx.esc(l)}</b></span></li>`;
      }).join("");
      el.innerHTML = `${ctx.head({ icon: "container", label: "Container", chip: pairs.some(Boolean) ? `${up}/${pairs.filter(Boolean).length}` : "", state: down ? "bad" : "ok" })}
        ${rows ? `<ul class="wk-list">${rows}</ul>` : `<div class="wk-empty"><span>In attesa di dati</span></div>`}`;
    },
  });
})();
