(() => {
  AtenaDesk.register("sun_cycle", {
    render(el, d, ctx) {
      const p = ctx.pct(d.progress) / 100;
      const q = 1 - p, x = q * q * 10 + 2 * q * p * 100 + p * p * 190, y = q * q * 58 + 2 * q * p * -34 + p * p * 58;
      const mins = Number(d.daylight_min) || 0;
      el.innerHTML = `${ctx.head({ icon: d.up ? "sun" : "moon", label: "Sole", title: d.place || "" })}
        <svg class="sc-arc" viewBox="0 0 200 64" aria-hidden="true">
          <path d="M10 58 Q100 -34 190 58" fill="none" stroke="rgba(255,255,255,.12)" stroke-width="1.2" stroke-dasharray="2 4"/>
          <line x1="0" y1="58.5" x2="200" y2="58.5" stroke="rgba(255,255,255,.08)"/>
          ${d.up ? `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4.5" fill="rgb(var(--tone))" style="filter:drop-shadow(0 0 6px rgb(var(--tone)))"/>` : ""}
        </svg>
        <dl class="wk-kv"><dt>Alba</dt><dd class="mono">${ctx.esc(d.sunrise)}</dd><dt>Tramonto</dt><dd class="mono">${ctx.esc(d.sunset)}</dd>
        <dt>Luce</dt><dd><span>${Math.floor(mins / 60)} h ${mins % 60} min</span></dd></dl>`;
    },
  });
})();
