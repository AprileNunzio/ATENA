(() => {
  AtenaDesk.register("git_diff", {
    render(el, d, ctx) {
      const all = String(d.content ?? "").slice(0, 20000).split("\n");
      const add = all.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
      const del = all.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
      const file = (all.find((l) => l.startsWith("+++ ")) || "").replace(/^\+\+\+ (b\/)?/, "");
      const out = all.slice(0, 60).map((l) => {
        const t = ctx.esc(l);
        if (l.startsWith("@@")) return `<em>${t}</em>`;
        if (l.startsWith("+++") || l.startsWith("---")) return `<span class="gd-meta">${t}</span>`;
        if (l.startsWith("+")) return `<span class="gd-add">${t}</span>`;
        if (l.startsWith("-")) return `<span class="gd-del">${t}</span>`;
        return t;
      }).join("\n");
      el.innerHTML = `${ctx.head({ icon: "git", label: "Modifiche", title: file, chip: add || del ? `+${add} −${del}` : "" })}
        ${out.trim() ? `<pre class="wk-pre">${out}</pre>` : `<div class="wk-empty"><span>Nessuna modifica</span></div>`}`;
    },
  });
})();
