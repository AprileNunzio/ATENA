(() => {
  AtenaDesk.register("rag_sources", {
    render(el, d, ctx) {
      const list = Array.isArray(d.sources) ? d.sources.slice(0, 8) : [];
      el.innerHTML = `${ctx.head({ icon: "book", label: "Fonti consultate", title: d.query ? `«${d.query}»` : "" })}
        <ul class="wk-list">${list.map((s) => `<li class="wk-row"><span><b>${ctx.esc(s.name)}</b>${ctx.bar(s.relevance)}</span>
          <span class="wk-val">${ctx.esc(Math.round(Number(s.relevance) || 0))}%</span></li>`).join("")}</ul>`;
    },
  });
})();
