(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const DURATIONS = [["30", "30 secondi"], ["60", "1 minuto"], ["120", "2 minuti"], ["300", "5 minuti"]];
  let values = {};

  const feature = () => ((A.featData && A.featData.features) || []).find((f) => f.id === "redalert") || {};

  function toggle(key, icon, title, text) {
    const on = values[key] !== "0";
    return `<label class="ra-toggle"><span class="ra-ic">${icon}</span><span><b>${fmt.esc(title)}</b><small>${fmt.esc(text)}</small></span>
      <input type="checkbox" data-key="${key}" ${on ? "checked" : ""}><i></i></label>`;
  }

  function render() {
    const f = feature(), off = !!(f.state && f.state.enabled === false);
    $("ra-body").innerHTML = `${off ? `<div class="ra-off">${fmt.esc("L'allarme rosso è spento: accendilo dalla scheda della funzionalità qui sopra.")}</div>` : ""}
      ${toggle("ATENA_REDALERT_LIGHTS", "💡", "Luci rosse", "Tutte le luci di Home Assistant lampeggiano piano, poi tornano come prima.")}
      ${toggle("ATENA_REDALERT_CAST", "📢", "Avviso a voce", "Il messaggio urgente si sente su tutti i Chromecast di casa.")}
      <div><div class="ra-label">Per quanto tempo</div><div class="ra-chips">${DURATIONS.map(([v, l]) => `<button type="button" class="ra-chip ${String(values.ATENA_REDALERT_SECONDS || "60") === v ? "on" : ""}" data-seconds="${v}">${fmt.esc(l)}</button>`).join("")}</div></div>
      <div class="ra-row"><button type="button" class="btn primary ra-big" id="ra-test" ${off ? "disabled" : ""}>▶ Prova per 12 secondi</button>
        <button type="button" class="btn ra-big" id="ra-stop">⏹ Ferma</button></div>`;
  }

  async function save(body) {
    try {
      const r = await A.api("PUT", "/api/features/redalert/settings", body);
      values = { ...values, ...(r.values || body) };
      A.toast("Salvato");
    } catch (e) { A.toast(e.message, true); }
    render();
  }

  async function load() {
    values = { ...(feature().values || {}) };
    render();
  }

  function init() {
    $("ra-body").addEventListener("change", (e) => {
      const key = e.target.dataset.key;
      if (key) save({ [key]: e.target.checked ? "1" : "0" });
    });
    $("ra-body").addEventListener("click", async (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.seconds) return save({ ATENA_REDALERT_SECONDS: b.dataset.seconds });
      try {
        if (b.id === "ra-test") { await A.api("POST", "/api/redalert/test"); A.toast("Prova in corso: luci e Chromecast per 12 secondi"); }
        if (b.id === "ra-stop") { await A.api("POST", "/api/redalert/stop"); A.toast("Allarme rosso fermato"); }
      } catch (err) { A.toast(err.message, true); }
      return undefined;
    });
  }

  A.tab("redalert", { title: "Allarme rosso", init, load });
})();
