(() => {
  const A = window.AtenaAdmin, { $ } = A;
  const C = A.cams;
  let timer = null;

  const ICON = { motion: "🏃" };

  async function load() {
    let d;
    try { d = await A.api("GET", "/api/cameras/events"); } catch (e) { $("cam-pane-events").innerHTML = `<div class="cam-err">${C.esc(e.message)}</div>`; return; }
    const rows = d.events.map((e) => `<div class="cam-row"><span>${ICON[e.kind] || "•"} ${C.esc(e.text)}</span><span class="faint">${C.when(e.at)}</span></div>`).join("");
    $("cam-pane-events").innerHTML = `<div class="panel"><div class="bio-line" style="justify-content:space-between"><div class="panel-title" style="margin:0">Eventi delle telecamere</div>
      <button class="btn sm" data-act="clear">Svuota</button></div>
      <div class="cam-list" style="margin-top:10px">${rows || '<div class="faint">Nessun evento. Attiva l\'avviso di movimento dalle opzioni di una telecamera.</div>'}</div></div>`;
    clearInterval(timer);
    timer = setInterval(() => { if (A.isOn("cameras") && C.pane === "events") load(); }, 5000);
  }

  function init() {
    $("cam-pane-events").addEventListener("click", async (e) => {
      if (!e.target.closest("[data-act=clear]")) return;
      try { await A.api("DELETE", "/api/cameras/events"); } catch (err) { A.toast(err.message, true); }
      load();
    });
  }

  function leave() { clearInterval(timer); }

  C.panes.events = { init, load, leave };
})();
