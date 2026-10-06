(() => {
  AtenaDesk.register("active_tasks", {
    render(el, d, ctx) {
      const tasks = (Array.isArray(d.tasks) ? d.tasks : []).slice(0, 10);
      const rows = tasks.map((t, i) => `<div class="wk-task${i === 0 ? " on" : ""}">${ctx.esc(t)}</div>`).join("");
      el.innerHTML = `${ctx.head({ icon: "brain", label: "Stato agente", chip: tasks.length ? `${tasks.length} attive` : "", live: tasks.length > 0 })}
        ${rows || `<div class="wk-empty">In attesa di istruzioni</div>`}`;
    },
  });
})();
