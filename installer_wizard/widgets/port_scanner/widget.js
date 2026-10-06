(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 8000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  AtenaDesk.register("port_scanner", {
    render(el, d, ctx) {
      const lines = plain(d.content).split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 12);
      let open = 0;
      const rows = lines.map((l) => {
        const m = l.match(/^(\d{1,5})\/(tcp|udp)\s+(\S+)\s*(.*)$/i);
        if (!m) return `<li class="wk-row"><span><small>${ctx.esc(l)}</small></span></li>`;
        const st = m[3].toLowerCase();
        const on = st === "open" || st === "aperta";
        if (on) open += 1;
        return `<li class="wk-row ic${on ? " on" : ""}">${ctx.icon("port")}<span><b class="wk-mono">${ctx.esc(m[1])}/${ctx.esc(m[2].toLowerCase())}</b><small>${ctx.esc(m[4] || "—")}</small></span><span class="wk-chip${on ? " warn" : ""}">${ctx.esc(st)}</span></li>`;
      }).join("");
      el.innerHTML = `${ctx.head({ icon: "port", label: "Scansione porte", chip: open ? `${open} aperte` : "", state: open ? "warn" : "" })}
        ${rows ? `<ul class="wk-list">${rows}</ul>` : `<div class="wk-empty"><span>In attesa di dati</span></div>`}`;
    },
  });
})();
