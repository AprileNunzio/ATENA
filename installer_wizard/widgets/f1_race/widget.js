(() => {
  const left = (iso) => {
    const s = Math.max(0, (new Date(iso).getTime() - Date.now()) / 1000);
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    return d ? `${d}g ${h}h` : h ? `${h}h ${m}m` : `${m} min`;
  };
  const at = (iso) => new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const rows = (list, ctx) => `<ul class="wk-list f1-rows">${list.map((r) => `<li class="wk-row ic"><span class="f1-pos">${ctx.esc(r.pos)}</span>
    <span>${ctx.esc(r.name || r.team || "")}${r.name && r.team ? `<small> ${ctx.esc(r.team)}</small>` : ""}</span><span class="mono">${ctx.esc(r.time || r.points)}</span></li>`).join("")}</ul>`;
  AtenaDesk.register("f1_race", {
    render(el, d, ctx) {
      const race = d.race || {};
      if (d.mode === "standings") {
        el.innerHTML = `${ctx.head({ icon: "trend", label: "Formula 1", title: "Mondiale piloti" })}${rows((d.drivers || []).slice(0, 6), ctx)}`;
        return;
      }
      if (d.mode === "results") {
        el.innerHTML = `${ctx.head({ icon: "star", label: "Formula 1", title: race.name || "", chip: "risultati" })}${rows((d.results || []).slice(0, 6), ctx)}`;
        return;
      }
      const s = d.session || {}, live = d.mode === "live";
      el.innerHTML = `${ctx.head({ icon: "car", label: "Formula 1", title: race.name || "", chip: live ? "in corso" : "prossima", live })}
        <div class="wk-hero"><span class="wk-num sm">${live ? "LIVE" : ctx.esc(left(s.start))}</span>
          <span class="wk-sub"><span>${ctx.esc(s.name || "")}</span><br><span>${ctx.esc(at(s.start))}</span></span></div>
        <dl class="wk-kv"><dt>Circuito</dt><dd>${ctx.esc(race.circuit || "")}</dd><dt>Luogo</dt><dd>${ctx.esc(race.place || "")}</dd><dt>Round</dt><dd class="mono">${ctx.esc(race.round || "")}</dd></dl>`;
    },
  });
})();
