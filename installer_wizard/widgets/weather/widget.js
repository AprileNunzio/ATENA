(() => {
  const ICON = (k) => (window.AtenaIcons ? window.AtenaIcons.weather(k) : "");
  AtenaDesk.register("weather", {
    render(el, d, ctx) {
      const c = d.current || {};
      const days = (d.days || []).slice(1, 5);
      el.innerHTML = `${ctx.head({ icon: "partly", label: "Meteo", title: d.location || "" })}
        <div class="wk-hero"><span class="wk-big">${ICON(c.icon)}</span><span class="wk-num">${ctx.esc(c.temp ?? "—")}<sup>°</sup></span>
          <span class="wk-sub"><span>${ctx.esc(c.desc || "")}</span><br><span>percepita ${ctx.esc(c.feels ?? "—")}° · vento ${ctx.esc(c.wind ?? "—")} km/h</span></span></div>
        <div class="wk-days">${days.map((x) => `<div><b>${ctx.esc(String(x.label || "").slice(0, 3))}</b>${ICON(x.icon)}
          <span>${ctx.esc(x.tmax)}° <small>${ctx.esc(x.tmin)}°</small></span>${x.rain >= 40 ? `<small class="wk-accent">${ctx.esc(x.rain)}%</small>` : ""}</div>`).join("")}</div>`;
    },
  });
})();
