(() => {
  AtenaDesk.register("kanban_board", {
    render(el, d, ctx) {
      const doing = Array.isArray(d.doing) ? d.doing.slice(0, 8) : [];
      const todo = Array.isArray(d.todo) ? d.todo.slice(0, 8) : [];
      const col = (title, list, on) => `<div class="wk-col"><h5>${title} · ${list.length}</h5>${list.map((t) => `<div class="wk-task${on ? " on" : ""}">${ctx.esc(t)}</div>`).join("")}</div>`;
      el.innerHTML = `${ctx.head({ icon: "board", label: "Attività dell'agente", chip: doing.length ? `${doing.length} in corso` : "", live: doing.length > 0 })}
        <div class="wk-cols">${col("In corso", doing, true)}${col("Da fare", todo, false)}</div>`;
    },
  });
})();
