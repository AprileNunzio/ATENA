(() => {
  AtenaDesk.register("reminder", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "bell", label: "Promemoria", chip: "in attesa", live: true })}
        <div class="wk-hero"><span class="wk-big">${ctx.icon("clock")}</span>
          <span class="wk-title">${d.content ? ctx.esc(String(d.content).slice(0, 200)) : "<span>Nuovo promemoria</span>"}</span></div>`;
    },
  });
})();
