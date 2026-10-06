(() => {
  AtenaDesk.register("thermostat", {
    render(el, d, ctx) {
      const cur = Number(d.current), target = Number(d.target);
      const fill = Number.isFinite(cur) ? ((cur - 10) / 20) * 100 : 0;
      el.innerHTML = `${ctx.head({ icon: "therm", label: "Clima", title: d.room || "", chip: d.status || "standby", live: !!d.status })}
        <div class="wk-hero" style="align-items:center">${ctx.ring(fill, Number.isFinite(cur) ? `${cur}°` : "—", "ora")}
          <dl class="wk-kv" style="flex:1"><dt>Obiettivo</dt><dd class="mono">${Number.isFinite(target) ? `${target}°` : "—"}</dd>
          <dt>Umidità</dt><dd>${ctx.esc(d.humidity ?? "—")}%</dd></dl></div>`;
    },
  });
})();
