(() => {
  AtenaDesk.register("alert_warning", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "alert", label: "Attenzione", chip: "avviso", state: "warn" })}
        <div class="wk-title">${ctx.esc(String(d.title || "Attenzione").slice(0, 120))}</div>
        ${d.content ? `<div class="wk-sub">${ctx.esc(String(d.content).slice(0, 600))}</div>` : ""}`;
    },
  });
})();
