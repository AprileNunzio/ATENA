(() => {
  AtenaDesk.register("cyber_alert", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "shield", label: "Sicurezza", title: d.title || "Accesso bloccato", chip: String(d.threat_level || "alert").toLowerCase(), live: true, state: "bad" })}
        <dl class="wk-kv"><dt>Origine</dt><dd class="mono wk-accent">${ctx.esc(d.source_ip || "—")}</dd>
        <dt>Attacco</dt><dd>${ctx.esc(d.attack_type || "—")}</dd><dt>Azione</dt><dd class="wk-accent">${ctx.esc(d.action_taken || "—")}</dd></dl>`;
    },
  });
})();
