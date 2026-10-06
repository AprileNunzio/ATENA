(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  const STATE = { installed: "installato", installing: "in installazione", queued: "in coda", failed: "errore", available: "su richiesta", removed: "rimosso" };
  const BADGE = { installed: "ok", installing: "running", queued: "warn", failed: "down" };
  const NOTE = {
    local: "I modelli girano su questo computer con Ollama: tutto resta in casa.",
    remote: "Uso Ollama di un altro computer della rete: qui non installo nulla del cervello.",
    cloud: "Le risposte arrivano dal servizio cloud configurato in Funzionalità › Cloud.",
    pending: "Il cervello non è ancora scelto: scegli dove deve pensare Atena.",
  };
  let mode = "pending";
  let pick = "local";

  function selectMode(m) {
    pick = m;
    for (const b of $("brain-mode").children) {
      b.classList.toggle("on", b.dataset.mode === m);
      b.setAttribute("aria-checked", String(b.dataset.mode === m));
    }
    $("brain-url").hidden = m !== "remote";
    $("brain-save").hidden = m === mode && m !== "remote";
  }

  function render(d) {
    mode = d.brain;
    $("brain-note").textContent = NOTE[mode] || "";
    selectMode(mode === "pending" ? "local" : mode);
    $("pkg-body").innerHTML = d.packages.map((p) => {
      const on = p.wanted;
      const action = p.state === "installing" ? ""
        : !on ? `<button class="btn sm primary" type="button" data-pkg="${fmt.esc(p.id)}" data-on="1">Installa</button>`
        : p.removable ? `<button class="btn sm" type="button" data-pkg="${fmt.esc(p.id)}" data-on="0">Rimuovi</button>` : "";
      return `<tr><td>${fmt.esc(p.title)}<div class="faint" style="font-size:12px">${fmt.esc(p.description)}${p.detected ? " · dispositivo rilevato" : ""}</div></td>
        <td class="mono">${Number(p.size_gb).toFixed(1)} GB</td>
        <td><span class="badge ${BADGE[p.state] || ""}">${STATE[p.state] || fmt.esc(p.state)}</span></td>
        <td style="text-align:right">${action}</td></tr>`;
    }).join("");
  }

  const load = () => A.api("GET", "/api/packages").then(render).catch((e) => A.toast(e.message, true));

  function init() {
    $("brain-mode").addEventListener("click", (e) => {
      const b = e.target.closest("[data-mode]");
      if (b) selectMode(b.dataset.mode);
    });
    $("brain-save").addEventListener("click", async () => {
      const b = $("brain-save");
      const body = { mode: pick };
      if (pick === "remote") body.url = $("brain-url").value.trim();
      if (pick !== mode && !confirm("Cambiare dove pensa Atena? I componenti necessari si installano in background.")) return;
      b.disabled = true;
      try { await A.api("POST", "/api/packages/brain", body); A.toast("Scelta salvata, applicazione in corso"); await load(); }
      catch (err) { A.toast(err.message, true); }
      finally { b.disabled = false; }
    });
    $("pkg-body").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-pkg]");
      if (!b) return;
      const on = b.dataset.on === "1";
      if (!on && !confirm("Rimuovere il pacchetto? Lo puoi reinstallare quando vuoi.")) return;
      b.disabled = true;
      try { await A.api("POST", `/api/packages/${encodeURIComponent(b.dataset.pkg)}`, { on }); A.toast(on ? "Installazione avviata in background" : "Pacchetto disattivato"); await load(); }
      catch (err) { A.toast(err.message, true); b.disabled = false; }
    });
    setInterval(() => { if (A.isOn("packages")) load(); }, 5000);
  }

  A.tab("packages", { title: "Pacchetti", init, load });
})();
