(() => {
  const dot = (c) => `#${/^[0-9a-f]{6}$/i.test(c || "") ? c : "29e0ff"}`;
  AtenaDesk.register("sport_table", {
    render(el, d, ctx) {
      const rows = d.rows || [], mark = new Set(d.highlight || []);
      const focus = rows.findIndex((r) => mark.has(r.id));
      const start = focus > 6 ? Math.max(0, focus - 3) : 0;
      const view = rows.slice(start, start + 8);
      el.innerHTML = `${ctx.head({ icon: "list", label: "Classifica", title: d.league_name || "" })}
        <table class="st-table"><thead><tr><th>#</th><th></th><th>G</th><th>DR</th><th>Pt</th></tr></thead><tbody>
        ${view.map((r) => `<tr class="${mark.has(r.id) ? "me" : ""}"><td>${ctx.esc(r.rank)}</td><td><i style="--team:${dot(r.color)}"></i>${ctx.esc(r.short || r.name || "")}</td>
          <td>${ctx.esc(r.played)}</td><td>${r.diff > 0 ? "+" : ""}${ctx.esc(r.diff)}</td><td><b>${ctx.esc(r.points)}</b></td></tr>`).join("")}</tbody></table>`;
    },
  });
})();
