(() => {
  AtenaDesk.register("home_rooms", {
    render(el, d, ctx) {
      const rooms = Array.isArray(d.rooms) ? d.rooms.slice(0, 12) : [];
      el.innerHTML = `${ctx.head({ icon: "home", label: "Casa", chip: rooms.length === 1 ? "1 occupata" : `${rooms.length} occupate`, live: rooms.length > 0 })}
        <ul class="wk-list">${rooms.map((r) => `<li class="wk-row ic on">${ctx.icon("door")}<b>${ctx.esc(r)}</b><span></span></li>`).join("")}</ul>`;
    },
  });
})();
