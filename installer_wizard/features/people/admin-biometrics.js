(() => {
  const A = window.AtenaAdmin, { $, fmt } = A;
  let timer = null;

  const badge = (text, kind = "") => `<span class="badge ${kind}">${fmt.esc(text)}</span>`;

  const qualityBadge = (q) => badge(q, q === "ottima" ? "ok" : q === "buona" ? "" : "warn");

  function row(p) {
    const f = p.face, v = p.voice;
    const similar = [...((f && f.similar) || []).map((s) => `volto simile a ${s.name} (${s.similarity})`),
      ...((v && v.similar) || []).map((s) => `voce simile a ${s.name} (${s.similarity})`)];
    return `<tr><td><b>${fmt.esc(p.name)}</b>${similar.length ? `<div class="bio-note" style="color:var(--amber)">⚠ ${similar.map(fmt.esc).join("; ")}: per distinguerli servono più campioni e un distacco maggiore</div>` : ""}</td>
      <td>${f ? `${f.samples} colori${f.samples_ir ? ` + ${f.samples_ir} infrarossi` : ""}<div class="bio-note">soglia ${f.threshold}</div>` : "—"}</td>
      <td>${v ? `${v.samples} campioni<div class="bio-note">soglia ${v.threshold}${v.enrolled ? "" : " · in raccolta"}</div>` : "—"}</td>
      <td>${f ? qualityBadge(f.quality) : ""}</td></tr>`;
  }

  async function loadTable() {
    let d;
    try { d = await A.api("GET", "/api/vision/biometrics"); } catch (e) { $("bio-table").textContent = e.message; return; }
    $("bio-table").innerHTML = d.people.length
      ? `<div class="bio-scroll"><table class="bio-table"><thead><tr><th>Persona</th><th>Volto</th><th>Voce</th><th>Qualità</th></tr></thead><tbody>${d.people.map(row).join("")}</tbody></table></div>
         <div class="bio-note">Il riconoscimento migliora da solo: aggiunge campioni diversi (angolazioni, luce) e scarta quelli ridondanti. Le persone che si somigliano ricevono una soglia più severa e non mescolano i loro campioni.</div>`
      : '<div class="faint">Nessuna persona registrata.</div>';
  }

  function init() {}

  function load() {
    loadTable();
    clearInterval(timer);
    timer = setInterval(() => { if (A.isOn("people")) loadTable(); }, 15000);
  }

  function leave() { clearInterval(timer); }

  A.peopleBio = { init, load, leave };
})();
