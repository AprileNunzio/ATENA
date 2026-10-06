(() => {
  const LABEL = { idle: "Di' «Atena»", listening: "Ti ascolto…", transcribing: "Sto capendo…", off: "Microfono non attivo" };
  AtenaDesk.register("listening", {
    render(el) {
      el.innerHTML = `<div class="ls-box idle"><span class="ls-ic">🎙</span><span class="ls-bars">${"<i></i>".repeat(10)}</span><span class="ls-t">${LABEL.idle}</span></div>`;
      const box = el.firstChild, bars = [...box.querySelectorAll(".ls-bars i")], text = box.querySelector(".ls-t");
      const onState = (e) => {
        const s = e.detail.state;
        box.className = `ls-box ${s}`;
        text.textContent = s === "off" ? (e.detail.text || LABEL.off).replace(/^Microfono non disponibile: /, "Microfono: ") : LABEL[s] || s;
      };
      const onLevel = (e) => {
        const v = e.detail;
        bars.forEach((b, i) => { b.style.height = `${3 + Math.max(0, v * 30 - Math.abs(i - 4.5) * 2 + Math.random() * 3)}px`; });
      };
      window.addEventListener("atena-ear", onState);
      window.addEventListener("atena-ear-level", onLevel);
      el._off = () => { window.removeEventListener("atena-ear", onState); window.removeEventListener("atena-ear-level", onLevel); };
      if (window.atenaEar) onState({ detail: { state: window.atenaEar.state } });
    },
    update() {},
    destroy(el) { if (el._off) el._off(); },
  });
})();
