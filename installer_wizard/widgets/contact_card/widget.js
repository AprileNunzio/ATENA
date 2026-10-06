(() => {
  AtenaDesk.register("contact_card", {
    render(el, d, ctx) {
      const name = String(d.name || "");
      el.innerHTML = `${ctx.head({ icon: "contact", label: "Contatto", title: d.company || "" })}
        <div class="wk-hero cc-hero"><span class="cc-ini">${name ? ctx.esc(name.charAt(0).toUpperCase()) : ctx.icon("user")}</span>
          <span><div class="wk-title">${name ? ctx.esc(name) : "<span>Sconosciuto</span>"}</div>
          <div class="wk-sub">${ctx.esc(d.company || "")}</div></span></div>
        <dl class="wk-kv cc-kv"><dt>Telefono</dt><dd class="mono wk-accent">${d.phone ? ctx.esc(d.phone) : "<span>Nessun numero</span>"}</dd>
        ${d.email ? `<dt>Email</dt><dd class="wk-faint">${ctx.esc(d.email)}</dd>` : ""}</dl>`;
    },
  });
})();
