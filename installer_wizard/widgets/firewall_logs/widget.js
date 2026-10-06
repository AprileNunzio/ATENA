(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 8000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  const IP = /\b(?:\d{1,3}\.){3}\d{1,3}\b|\b[0-9a-f]{1,4}(?::[0-9a-f]{0,4}){2,7}\b/gi;
  AtenaDesk.register("firewall_logs", {
    render(el, d, ctx) {
      const lines = plain(d.content).split("\n").map((l) => l.trim()).filter(Boolean).slice(-14);
      const out = lines.map((l) => ctx.esc(l).replace(IP, (m) => `<em>${m}</em>`)).join("\n");
      el.innerHTML = `${ctx.head({ icon: "shield", label: "Firewall", chip: lines.length ? `${lines.length} bloccati` : "", live: lines.length > 0, state: "bad" })}
        ${out ? `<pre class="wk-pre">${out}</pre>` : `<div class="wk-empty"><span>Nessun pacchetto bloccato</span></div>`}`;
    },
  });
})();
