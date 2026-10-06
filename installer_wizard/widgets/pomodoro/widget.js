(() => {
  AtenaDesk.register("pomodoro", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "tomato", label: "Pomodoro", title: "concentrazione" })}
        <div class="wk-text">${d.content ? ctx.esc(String(d.content).slice(0, 400)) : "<span>Preparazione del timer…</span>"}</div>`;
    },
  });
})();
