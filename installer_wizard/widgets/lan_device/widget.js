(() => {
  AtenaDesk.register("lan_device", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "lan", label: "Nuovo dispositivo", title: d.hostname || "", chip: "in rete", live: true })}
        <dl class="wk-kv"><dt>IP</dt><dd class="mono">${ctx.esc(d.ip || "—")}</dd><dt>MAC</dt><dd class="mono wk-faint">${ctx.esc(d.mac || "—")}</dd>
        <dt>Produttore</dt><dd>${ctx.esc(d.vendor || "—")}</dd></dl>`;
    },
  });
})();
