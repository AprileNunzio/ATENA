(() => {
  AtenaDesk.register("usb_monitor", {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "usb", label: "Nuovo dispositivo USB", chip: "collegato", live: true })}
        <div class="wk-hero"><span class="wk-num sm">${ctx.esc(d.size || "—")}</span><span class="wk-sub">${ctx.esc(d.vendor || "—")}</span></div>
        <dl class="wk-kv" style="margin-top:10px"><dt>Montato su</dt><dd class="mono">${ctx.esc(d.mount || "—")}</dd>
        <dt>Prodotto</dt><dd>${ctx.esc(d.product || "—")}</dd><dt>Seriale</dt><dd class="mono wk-faint">${ctx.esc(d.serial || "—")}</dd></dl>`;
    },
  });
})();
