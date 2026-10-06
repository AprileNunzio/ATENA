(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 6000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  const state = (v) => {
    if (/fail|error|errore|fallit|cancel|annullat/i.test(v)) return "bad";
    if (/running|in corso|pending|in attesa|queued|coda/i.test(v)) return "live";
    if (/success|passed|riuscit|superat|completat|\bok\b|done/i.test(v)) return "ok";
    return "";
  };
  AtenaDesk.register("cicd_tracker", {
    render(el, d, ctx) {
      const lines = plain(d.content).split("\n").map((l) => l.trim()).filter(Boolean).slice(0, 10);
      const pairs = lines.map((l) => l.match(/^([^:]{1,48}):\s+(.+)$/));
      const states = pairs.map((p) => (p ? state(p[2]) : ""));
      const failed = states.filter((s) => s === "bad").length;
      const running = states.filter((s) => s === "live").length;
      const rows = lines.map((l, i) => {
        const p = pairs[i];
        const s = states[i];
        const cls = s === "bad" ? " bad" : s === "live" ? " on" : "";
        return p
          ? `<li class="wk-row ic${cls}">${ctx.icon(s === "bad" ? "error" : s === "ok" ? "check" : "pipeline")}<span><b>${ctx.esc(p[1])}</b></span><span class="wk-chip${s === "live" ? " live" : s ? ` ${s}` : ""}">${ctx.esc(p[2])}</span></li>`
          : `<li class="wk-row"><span><b>${ctx.esc(l)}</b></span></li>`;
      }).join("");
      const chip = failed ? `${failed} fallite` : running ? `${running} in corso` : "";
      el.innerHTML = `${ctx.head({ icon: "pipeline", label: "Pipeline CI/CD", chip, live: !failed && running > 0, state: failed ? "bad" : "" })}
        ${rows ? `<ul class="wk-list">${rows}</ul>` : `<div class="wk-empty"><span>In attesa di dati</span></div>`}`;
    },
  });
})();
