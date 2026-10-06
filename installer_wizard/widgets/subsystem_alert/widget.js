(() => {
  AtenaDesk.register("subsystem_alert", {
    render(el, d, ctx) {
      const items = Array.isArray(d.items) ? d.items.slice(0, 8) : [];
      el.innerHTML = `${ctx.head({ icon: "alert", label: "Sistema", title: "Riparazione in corso", chip: items.length === 1 ? "1 guasto" : `${items.length} guasti`, live: true, state: "bad" })}
        <ul class="wk-list">${items.map((i) => `<li class="wk-row bad"><span><b>${ctx.esc(i.label)}</b><small>${ctx.esc(i.detail)}</small></span><span></span></li>`).join("")}</ul>`;
    },
  });
})();
