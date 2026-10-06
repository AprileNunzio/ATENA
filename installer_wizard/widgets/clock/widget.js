(() => {
  const timers = new WeakMap();
  const lang = () => (document.documentElement.lang === "en" ? "en-GB" : "it-IT");
  const week = (d) => {
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
    return Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
  };
  function tick(el) {
    const now = new Date();
    const hm = el.querySelector(".ck-hm"), sec = el.querySelector(".ck-s"), day = el.querySelector(".ck-day");
    if (!hm) return;
    hm.textContent = now.toLocaleTimeString(lang(), { hour: "2-digit", minute: "2-digit" });
    sec.textContent = String(now.getSeconds()).padStart(2, "0");
    day.textContent = now.toLocaleDateString(lang(), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    el.querySelector(".ck-week").textContent = String(week(now));
    el.querySelector(".ck-bar > i").style.width = `${((now.getHours() * 60 + now.getMinutes()) / 1440) * 100}%`;
  }
  const impl = {
    render(el, d, ctx) {
      el.innerHTML = `${ctx.head({ icon: "clock", label: "Ora" })}
        <div class="wk-hero"><span class="wk-num ck-hm"></span><span class="wk-num sm wk-faint ck-s"></span></div>
        <div class="wk-sub ck-day"></div>
        <div class="wk-sub"><span>Settimana</span> <span class="wk-mono ck-week"></span></div>
        <span class="wk-bar ck-bar"><i></i></span>`;
      tick(el);
      clearInterval(timers.get(el));
      timers.set(el, setInterval(() => tick(el), 1000));
    },
    update(el) { tick(el); },
    destroy(el) { clearInterval(timers.get(el)); },
  };
  AtenaDesk.register("clock", impl);
})();
