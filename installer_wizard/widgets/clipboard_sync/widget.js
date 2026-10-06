(() => {
  const plain = (v) => {
    const s = String(v ?? "").slice(0, 4000).replace(/<br\s*\/?>/gi, "\n").replace(/<\/(p|div|li|tr|h[1-6])>/gi, "\n");
    return s.includes("<") ? new DOMParser().parseFromString(s, "text/html").body.textContent : s;
  };
  AtenaDesk.register("clipboard_sync", {
    render(el, d, ctx) {
      const text = plain(d.content).trim();
      el.innerHTML = `${ctx.head({ icon: "clipboard", label: "Appunti condivisi", chip: text ? `${text.length} caratteri` : "" })}
        ${text ? `<pre class="wk-pre">${ctx.esc(text)}</pre>` : `<div class="wk-empty"><span>Appunti vuoti</span></div>`}`;
    },
  });
})();
