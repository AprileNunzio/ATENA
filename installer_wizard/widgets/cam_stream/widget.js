(() => {
  AtenaDesk.register("cam_stream", {
    render(el, d, ctx) {
      const motion = !!d.motion_detected;
      el.innerHTML = `${ctx.head({ icon: "camera", label: "Videocamera", title: d.camera || "", chip: motion ? "movimento" : "in ascolto", live: true, state: motion ? "bad" : "" })}
        <div class="wk-media cs-feed"><span class="wk-faint wk-mono"><span>Flusso RTSP non disponibile</span></span></div>
        <dl class="wk-kv cs-kv"><dt>Sorgente</dt><dd>${ctx.esc(d.camera || "—")}</dd>
        <dt>Stato</dt><dd class="${motion ? "wk-accent" : "wk-faint"}"><span>${motion ? "Movimento rilevato" : "Nessun movimento"}</span></dd></dl>`;
    },
  });
})();
