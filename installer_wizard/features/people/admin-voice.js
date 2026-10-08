(() => {
  const A = window.AtenaAdmin, { fmt } = A;
  const ADVICE = { lower: "il microfono era troppo alto", raise: "la voce arrivava troppo bassa", ok: "livello del microfono corretto" };

  function chips(list) {
    return `<div class="caps">${list.map((v) => `<span>${fmt.esc(v)}</span>`).join("")}</div>`;
  }

  function dictionary(rows) {
    if (!rows.length) return '<div class="muted-note">ATENA ha capito tutte le frasi esattamente come scritte.</div>';
    return `<div style="overflow-x:auto"><table><thead><tr><th>Frase da dire</th><th>Come l'ha capita ATENA</th></tr></thead>
      <tbody>${rows.map((r) => `<tr><td>${fmt.esc(r.said)}</td><td>${fmt.esc(r.heard)}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function training(t) {
    if (!t) {
      return `<div class="muted-note" style="margin-top:10px">Non ancora addestrata. Premi «Avvia sul display»: sul display comparirà
        una breve sequenza da ripetere (il nome «Atena», alcuni comandi e qualche frase). ATENA impara il timbro della voce e il modo
        in cui questa persona pronuncia il suo nome e i comandi.</div>`;
    }
    const when = new Date(t.trained_at * 1000).toLocaleString();
    return `<div class="form-grid" style="margin-top:12px">
        <div><label>Ultimo addestramento</label><div>${fmt.esc(when)} · ${fmt.esc((t.language || "it").toUpperCase())}</div></div>
        <div><label>Frasi capite</label><div><b style="color:var(--cyan)">${t.score}%</b></div></div>
        <div><label>Microfono</label><div>${fmt.esc(ADVICE[(t.level && t.level.advice) || "ok"])}</div></div>
      </div>
      <label style="margin-top:14px">Come pronuncia «Atena»</label>
      ${(t.wake_variants || []).length ? chips(t.wake_variants) : '<div class="muted-note">Nessuna variante: il nome viene capito correttamente.</div>'}
      <label style="margin-top:14px">Dizionario personale</label>
      ${dictionary(t.dictionary || [])}`;
  }

  A.PeopleVoice = {
    section(p, base) {
      const t = p.voice_training;
      return `${base}
        <div class="panel-title" style="margin-top:22px">Addestramento vocale e dizionario personale</div>
        <div class="row" style="flex-wrap:wrap; gap:8px">
          <button class="btn primary" id="train-voice">🎙 Avvia sul display</button>
          ${t ? '<button class="btn sm danger" id="forget-training">Cancella dizionario</button>' : ""}
        </div>
        ${training(t)}`;
    },
    async handle(target, slug, reload) {
      if (target.id === "train-voice") {
        await A.api("POST", `/api/people/${encodeURIComponent(slug)}/voice-training/start`);
        A.toast("Addestramento avviato: segui le istruzioni sul display, davanti al microfono");
        return true;
      }
      if (target.id === "forget-training") {
        if (!confirm("Cancellare il dizionario vocale di questa persona?")) return true;
        await A.api("DELETE", `/api/people/${encodeURIComponent(slug)}/voice-training`);
        A.toast("Dizionario vocale cancellato");
        reload();
        return true;
      }
      return false;
    },
  };
})();
