(() => {
  AtenaDesk.register("study", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "study", label: "Studio", title: d.level ? String(d.level).slice(0, 40) : "", chip: "in corso", live: true })}
        <div class="wk-title">${d.topic ? ctx.esc(String(d.topic).slice(0, 80)) : "<span>Studio autonomo</span>"}</div>
        ${d.detail ? `<div class="wk-sub st-d">${ctx.esc(String(d.detail).slice(0, 240))}</div>` : ""}`;
    },
  });
})();
