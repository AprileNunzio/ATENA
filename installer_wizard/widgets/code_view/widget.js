(() => {
  function copy(text, button) {
    const done = () => { button.textContent = "Copiato"; setTimeout(() => { button.textContent = "Copia"; }, 1500); };
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(done).catch(() => fallback(text, done));
    fallback(text, done);
  }

  function fallback(text, done) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); done(); } catch (err) { console.warn(err); }
    area.remove();
  }

  AtenaDesk.register("code_view", {
    render(el, d, ctx) {
      const content = String(d.content || "");
      const lines = content.split("\n").length;
      el.innerHTML = `${ctx.head({ icon: "code", label: String(d.language || "testo").slice(0, 24), title: String(d.title || "").slice(0, 120), chip: `${lines} righe` })}
        <pre class="wk-pre cv-code"><code>${ctx.esc(content)}</code></pre>
        <div class="wk-actions"><button class="wk-btn primary cv-copy" type="button">Copia</button></div>`;
      el.querySelector(".cv-copy").addEventListener("click", (e) => { e.stopPropagation(); copy(content, e.currentTarget); });
    },
  });
})();
