(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 8000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  AtenaDesk.register("thinking_tree", {
    render(el, d, ctx) {
      const lines = plain(d.content).split("\n").map((l) => l.replace(/\s+$/, "")).filter((l) => l.trim()).slice(0, 24);
      const out = lines.map((l) => (/^\S/.test(l) || /[✓✔]/.test(l) ? `<em>${ctx.esc(l)}</em>` : ctx.esc(l))).join("\n");
      el.innerHTML = `${ctx.head({ icon: "tree", label: "Ragionamento", chip: lines.length ? `${lines.length} passi` : "" })}
        ${out ? `<pre class="wk-pre">${out}</pre>` : `<div class="wk-empty"><span>In attesa di dati</span></div>`}`;
    },
  });
})();
