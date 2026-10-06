(() => {
  AtenaDesk.register("route", {
    render(el, d, ctx) {
      const delay = Number(d.delay);
      const late = Number.isFinite(delay) && delay >= 3;
      const chip = late ? `+${Math.round(delay)} min traffico` : d.traffic ? "traffico scorrevole" : "";
      el.innerHTML = `${ctx.head({ icon: "car", label: d.mode || "viaggio", title: d.title || "", chip, state: late ? "warn" : "ok" })}
        <div class="wk-hero"><span class="wk-num sm">${ctx.esc(d.duration || "—")}</span>
          <span class="wk-sub">${ctx.esc(d.to || "")}<br>${ctx.esc(d.distance || "")}${d.via ? ` · ${ctx.esc(d.via)}` : ""}</span></div>
        <dl class="wk-kv" style="margin-top:12px">${d.leave_by ? `<dt>Parti entro</dt><dd class="mono wk-accent">${ctx.esc(d.leave_by)}</dd>` : ""}
          <dt>${d.leave_by ? "Appuntamento" : "Arrivo"}</dt><dd class="mono">${ctx.esc(d.arrive_at || "—")}</dd></dl>`;
    },
  });
})();
