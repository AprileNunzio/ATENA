(() => {
  AtenaDesk.register("alert_info", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "info", label: "Informazione" })}
        <div class="wk-title">${ctx.esc(String(d.title || "Informazione").slice(0, 120))}</div>
        ${d.content ? `<div class="wk-sub">${ctx.esc(String(d.content).slice(0, 600))}</div>` : ""}`;
    },
  });
})();
