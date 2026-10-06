(() => {
  AtenaDesk.register("alert_error", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "error", label: "Errore", chip: "critico", live: true, state: "bad" })}
        <div class="wk-title">${ctx.esc(String(d.title || "Errore di sistema").slice(0, 120))}</div>
        ${d.content ? `<div class="wk-text wk-faint">${ctx.esc(String(d.content).slice(0, 600))}</div>` : ""}`;
    },
  });
})();
