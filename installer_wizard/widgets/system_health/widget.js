(() => {
  const ICON = { Processore: "cpu", Memoria: "memory", Disco: "server", Temperatura: "therm" };
  AtenaDesk.register("system_health", {
    render(el, d, ctx) {
      const items = Array.isArray(d.items) ? d.items.slice(0, 6) : [];
      const state = (p) => (p >= 90 ? "bad" : p >= 75 ? "warn" : "");
      el.innerHTML = `${ctx.head({ icon: "gauge", label: "Sistema", title: "Risorse" })}
        ${items.length ? `<ul class="wk-list">${items.map((i) => `<li class="wk-row ic${state(i.percent) ? ` ${state(i.percent)}` : ""}">${ctx.icon(ICON[i.label] || "chip")}
          <span><b>${ctx.esc(i.label)}</b>${ctx.bar(i.percent, state(i.percent))}</span><span class="wk-val">${ctx.esc(i.value)}</span></li>`).join("")}</ul>`
          : `<div class="wk-empty">Dati non ancora disponibili</div>`}`;
    },
  });
})();
