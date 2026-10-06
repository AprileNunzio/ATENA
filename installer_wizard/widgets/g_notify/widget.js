(() => {
  const timers = new Map();
  const R = 26, C = 2 * Math.PI * R;
  const GROUP_ICON = { birthday: "gift", event: "calendar", appointment: "clock" };

  function countdown(el, at, ctx) {
    const left = Math.max(0, at - ctx.now());
    const span = el.querySelector(".gn-left"), arc = el.querySelector(".gn-arc");
    if (span) span.textContent = left >= 3600 ? `${Math.floor(left / 3600)}h ${Math.floor((left % 3600) / 60)}m` : ctx.mmss(left);
    if (arc) arc.style.strokeDashoffset = `${C * (1 - Math.min(1, left / 1800))}`;
  }

  function body(d, ctx) {
    if (d.kind === "event") {
      return `${ctx.head({ icon: "calendar", label: "Appuntamento", title: d.who || "", chip: "in arrivo", live: true })}
        <div class="wk-hero gn-hero"><span class="gn-ring"><svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="${R}" class="gn-track"/>
          <circle cx="32" cy="32" r="${R}" class="gn-arc" stroke-dasharray="${C}"/></svg><b class="gn-left">—</b></span>
          <span class="gn-main"><span class="wk-title">${ctx.esc(d.title || "")}</span>${d.text ? `<span class="wk-sub">${ctx.icon("pin")} ${ctx.esc(d.text)}</span>` : ""}</span></div>`;
    }
    if (d.kind === "brief") {
      const items = Array.isArray(d.items) ? d.items.slice(0, 3) : [];
      const groups = Array.isArray(d.groups) ? d.groups.slice(0, 4) : [];
      return `${ctx.head({ icon: "sun", label: "La tua giornata", title: d.who || "" })}
        ${items.length ? `<div class="wk-cols three gn-stats">${items.map((x) => `<div class="wk-col"><span class="wk-num sm">${ctx.esc(x.value)}</span><h5>${ctx.esc(x.label)}</h5></div>`).join("")}</div>` : ""}
        ${groups.map((g) => {
          const entries = Array.isArray(g.entries) ? g.entries : [];
          return `<div class="wk-col gn-group"><h5>${ctx.esc(g.label)}</h5><ul class="wk-list">${entries.slice(0, 4).map((e) => `<li class="wk-row ic">${ctx.icon(GROUP_ICON[g.key] || "bell")}
            <span><b>${ctx.esc(e.title)}</b>${e.where ? `<small>${ctx.esc(e.where)}</small>` : ""}</span><span class="wk-val">${ctx.esc(e.time || "")}</span></li>`).join("")}</ul>
            ${entries.length > 4 ? `<div class="wk-faint gn-more"><span>e altri ${ctx.esc(entries.length - 4)}</span></div>` : ""}</div>`;
        }).join("")}
        ${d.text && !groups.length ? `<div class="wk-text">${ctx.esc(d.text)}</div>` : ""}`;
    }
    return `${ctx.head({ icon: "mail", label: "Nuova email", title: d.who || "", chip: "nuova", live: true })}
      ${d.from ? `<div class="wk-sub">${ctx.esc(d.from)}</div>` : ""}<div class="wk-title">${ctx.esc(d.title || "")}</div>
      ${d.text ? `<div class="wk-sub gn-text">${ctx.esc(d.text)}</div>` : ""}`;
  }

  function render(el, d, ctx) {
    clearInterval(timers.get(el));
    el.innerHTML = body(d, ctx);
    if (d.kind === "event" && d.at) {
      countdown(el, d.at, ctx);
      timers.set(el, setInterval(() => countdown(el, d.at, ctx), 1000));
    }
  }

  AtenaDesk.register("g_notify", { render, update: render, destroy(el) { clearInterval(timers.get(el)); } });
})();
