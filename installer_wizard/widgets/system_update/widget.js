(() => {
  AtenaDesk.register("system_update", {
    render(el, d, ctx) {
      const changes = Array.isArray(d.changes) ? d.changes.slice(0, 6) : [];
      el.innerHTML = `${ctx.head({ icon: "download", label: "Aggiornamento", chip: "disponibile", live: true })}
        <dl class="wk-kv"><dt>Installata</dt><dd class="mono wk-faint">${ctx.esc(d.local || "—")}</dd><dt>Nuova</dt><dd class="mono wk-accent">${ctx.esc(d.remote || "—")}</dd></dl>
        ${changes.length ? `<ul class="wk-list">${changes.map((c) => `<li class="wk-row"><b>${ctx.esc(c)}</b><span></span></li>`).join("")}</ul>` : ""}`;
    },
  });
})();
