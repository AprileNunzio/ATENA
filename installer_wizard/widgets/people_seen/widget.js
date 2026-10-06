(() => {
  AtenaDesk.register("people_seen", {
    render(el, d, ctx) {
      const items = (Array.isArray(d.items) ? d.items : []).filter((i) => i && i.label && i.label !== "Nessuno").slice(0, 8);
      el.innerHTML = `${ctx.head({ icon: "eye", label: "Chi vedo" })}
        ${items.length ? `<ul class="wk-list">${items.map((i) => `<li class="wk-row ic${i.status === "ok" ? " on" : ""}">${ctx.icon(i.status === "ok" ? "user" : "users")}
          <b>${ctx.esc(i.label)}</b><span class="wk-val">${ctx.esc(i.value)}</span></li>`).join("")}</ul>`
          : `<div class="wk-empty">Non vedo nessuno</div>`}`;
    },
  });
})();
