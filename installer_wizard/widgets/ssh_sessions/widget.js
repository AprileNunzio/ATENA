(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 6000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  AtenaDesk.register("ssh_sessions", {
    render(el, d, ctx) {
      const lines = plain(d.content).split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 10);
      const rows = lines.map((l) => {
        const p = l.match(/^([^:]{1,64}):\s+(.+)$/);
        const root = /^root@/i.test(p ? p[1] : l);
        return p
          ? `<li class="wk-row ic${root ? " warn" : ""}">${ctx.icon("terminal")}<span><b>${ctx.esc(p[1])}</b></span><span class="wk-val">${ctx.esc(p[2])}</span></li>`
          : `<li class="wk-row ic${root ? " warn" : ""}">${ctx.icon("terminal")}<span><b>${ctx.esc(l)}</b></span></li>`;
      }).join("");
      el.innerHTML = `${ctx.head({ icon: "terminal", label: "Sessioni SSH", chip: lines.length ? `${lines.length} attive` : "", live: lines.length > 0 })}
        ${rows ? `<ul class="wk-list">${rows}</ul>` : `<div class="wk-empty"><span>Nessuna sessione attiva</span></div>`}`;
    },
  });
})();
