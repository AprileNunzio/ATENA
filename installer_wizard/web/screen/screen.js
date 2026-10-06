(() => {
  const $ = (id) => document.getElementById(id);
  const q = new URLSearchParams(location.search);
  const n = Math.max(1, +(q.get("n") || 1)), x = +(q.get("x") || 0);
  $("screen-name").textContent = `SCHERMO ${n + 1}`;

  function tick() {
    const d = new Date();
    $("clock").textContent = d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
    $("date").textContent = Atena.fmt.date(d);
  }

  function onState(s) {
    if (!["READY", "DEGRADED"].includes(s.phase)) return;
    if (s.asset_version && window.ATENA_ASSET_V && s.asset_version !== window.ATENA_ASSET_V) { location.reload(); return; }
    AtenaDesk.setScreens(s.screens);
    AtenaDesk.render(s.desk || []);
  }

  AtenaDesk.mount($("desk"), { screen: n, x, satellite: true, speak: () => {} });
  setInterval(tick, 1000); tick();
  Atena.connectState("/api/stream", onState, (ok) => $("link").classList.toggle("show", !ok));
})();
