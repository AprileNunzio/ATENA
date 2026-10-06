(() => {
  AtenaDesk.register("net_topology", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "network", label: "Rete", title: "mappa LAN" })}
        <div class="wk-text">${d.content ? ctx.esc(String(d.content).slice(0, 600)) : "<span>Caricamento della mappa di rete…</span>"}</div>`;
    },
  });
})();
